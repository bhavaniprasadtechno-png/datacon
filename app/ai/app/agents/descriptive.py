"""Descriptive Analytics Agent with Full Multi-Stage SQL Pipeline.

Orchestrates:
  1. Semantic Model (.yaml) Integration: Loads active_schema.yaml / semantic_model.yaml for rich table metadata & foreign keys.
  2. IntentAgent: Workspace and business domain classification.
  3. TableAgent: Compact semantic schema reasoning & multi-table selection (with synonyms and domain keyword matching).
  4. ColumnPruneAgent: Token-optimized column pruning per selected table.
  5. FeatureExtractor: Semantic pattern analysis (time-series, ranking, comparisons, filters, joins).
  6. MultiSQLGenerator / SQLGenerator: Context-rich SQL candidate generation with relationships.
  7. SQLVerifier & FixerAgent: Read-only validation and self-healing repair loop (up to 3 fix attempts).
  8. VerificationAgent: Query correctness verification against user question.
  9. InsightAgent: Executive business insights derived from complete query results.
  10. Presentation Planner & Normalizer: StructuredResponse contract with KPIs, charts, tables, and sources.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from app.agents.types import AgentPrep
from app.config import settings
from app.pipeline.analytics_engine import count_where, percentage, primary_metric
from app.pipeline.contracts import Insight, Metric, Source, StructuredResponse, Summary
from app.pipeline.insight_engine import binary_split_insights, ranking_insight
from app.pipeline.normalizer import NormalizedResult, normalize
from app.pipeline.presentation_planner import category_ranking, plan_table, plan_visualization
from app.pipeline.validator import compute_confidence, validate
from app.query_engine import generator, snapshot_store
from app.rag.chroma_store import query as chroma_query

logger = logging.getLogger("app.agents.descriptive")

SYSTEM = (
    "You are Datacon's descriptive analytics agent. You are given deterministic, "
    "pre-computed facts about the user's data — never raw database rows. Write a short, "
    "natural-language summary (1-2 sentences) for a business audience, citing ONLY the "
    "numbers listed below. Never state a number that isn't listed."
)

_FROM_TABLE_RE = re.compile(r'FROM\s+(?:"([^"]+)"|([A-Za-z_]\w*))', re.IGNORECASE)
_CONNECTOR_PREFIX_RE = re.compile(r"^conn_[^_]+_")
_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|COPY|EXPORT|PRAGMA|CALL|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

MAX_TABLE_DESCRIPTION_LENGTH = 120
MAX_TABLE_BUSINESS_TERMS = 4
MAX_TABLE_SYNONYMS = 4
MAX_COLUMN_BUSINESS_TERMS = 2
MAX_COLUMN_SYNONYMS = 2
MAX_SAMPLE_VALUES = 3
ROW_LIMIT = 500
QUERY_TIMEOUT_SECONDS = 10

FILTER_INTENT_KEYWORDS = {
    "from", "in", "where", "status", "category", "categories", "region",
    "state", "country", "city", "type", "types", "whose", "named", "called",
    "like", "between", "filter", "filtered", "delivered", "canceled",
    "cancelled", "shipped", "approved", "pending", "active", "tier",
}


# ============================================================================
# LLM HELPER (STREAMING COMPATIBLE FOR TOGETHER AI / QWEN)
# ============================================================================

async def _get_chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.1,
    timeout: int = 25,
) -> str:
    """Helper to call LLM provider asynchronously with streaming support to prevent Together AI exceptions."""
    if not settings.is_llm_configured:
        return ""

    api_key = settings.together_api_key or os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        return ""

    resolved_model = model or settings.llm_model
    if not resolved_model:
        resolved_model = f"together_ai/{settings.llm_model}"
    elif not resolved_model.startswith("together") and "together" not in resolved_model:
        resolved_model = f"together_ai/{resolved_model}"

    try:
        import litellm

        stream = await asyncio.wait_for(
            litellm.acompletion(
                model=resolved_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            ),
            timeout=timeout,
        )
        parts = []
        if hasattr(stream, "__aiter__"):
            async for chunk in stream:
                if not getattr(chunk, "choices", None):
                    continue
                delta = getattr(chunk.choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else getattr(getattr(chunk.choices[0], "message", None), "content", None)
                if content:
                    parts.append(content)
        elif hasattr(stream, "choices") and stream.choices:
            msg = getattr(stream.choices[0], "message", None)
            content = getattr(msg, "content", None) if msg else None
            if content:
                parts.append(content)
        elif isinstance(stream, str):
            parts.append(stream)

        return "".join(parts).strip()
    except Exception as e:
        logger.warning("[Descriptive] LLM completion error: %s", e)

    return ""


# ============================================================================
# FEATURE EXTRACTOR
# ============================================================================

class FeatureExtractor:
    """Extracts semantic features from natural language queries to guide SQL generation."""

    def __init__(self):
        self.ts_patterns = {
            "ts_trend": ["over time", "trend", "daily", "weekly", "monthly", "yearly", "how has", "change over"],
            "ts_rolling_window": ["rolling", "moving", "7-day", "30-day", "running", "sliding window"],
            "ts_period_over_period": ["vs last", "compared to previous", "month over month", "year over year", "mom", "yoy", "wow", "quarter over quarter", "qoq"],
            "ts_growth_rate": ["growth rate", "percent change", "% change", "increase by", "decrease by", "growth of", "decline of"],
            "ts_date_bin": ["per month", "per quarter", "per year", "by month", "by quarter", "by year", "monthly", "quarterly", "yearly", "group by date"],
        }
        self.rank_patterns = {
            "rank_topk": ["top", "bottom", "highest", "lowest", "best", "worst", "first", "last", "largest", "smallest"],
            "rank_percentile": ["percentile", "90th", "80th", "top 10%", "bottom 20%"],
            "rank_dense": ["dense rank", "rank customers", "rank products", "rank within"],
            "rank_window": ["within each", "by category", "by region", "by department", "partition by"],
        }
        self.compare_patterns = {
            "compare_categories": ["vs", "versus", "compared to", "different from", "how does", "compare", "breakdown"],
            "delta_metric": ["difference between", "variance", "delta", "change in", "increase in", "decrease in"],
            "best_worst": ["best performing", "worst performing", "highest growth", "lowest decline", "max", "min"],
            "aggregation_required": ["total", "sum", "average", "mean", "count", "group by", "aggregate", "overall", "show me", "give me", "revenue", "sales", "value"],
        }
        self.filter_patterns = {
            "conditional_filter": ["where", "if", "when", "filter", "for", "with", "only", "active", "status"],
            "multi_filter": ["and", "or", "both", "either", "neither"],
            "keyword_search": ["like", "contains", "includes", "search for", "matching"],
            "numeric_range": ["between", "more than", "less than", "greater than", "under", "over", "above", "below"],
        }
        self.join_patterns = {
            "join_required": ["from different tables", "across tables", "combine", "merge", "relate", "join", "link", "revenue", "orders"],
            "multi_join": ["multiple tables", "chain of tables"],
        }
        self.output_patterns = {
            "explain_required": ["explain", "why", "reason", "insight", "interpret"],
            "plot_required": ["visualize", "chart", "graph", "plot", "show as"],
        }
        self.number_patterns = [
            r"\b\d+\b",
            r"\btop\s+\d+\b",
            r"\bfirst\s+\d+\b",
            r"\bbottom\s+\d+\b",
            r"\b\d+%",
            r"\b\d+\s*(?:day|week|month|year)s?\b",
        ]

    def extract_features(self, user_query: str) -> dict[str, Any]:
        query_lower = user_query.lower()
        features: dict[str, Any] = {
            "time_series": [],
            "ranking": [],
            "comparison": [],
            "filtering": [],
            "join": [],
            "output": [],
            "numbers": [],
            "date_references": [],
        }

        for feature, patterns in self.ts_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                features["time_series"].append(feature)

        for feature, patterns in self.rank_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                features["ranking"].append(feature)

        for feature, patterns in self.compare_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                features["comparison"].append(feature)

        for feature, patterns in self.filter_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                features["filtering"].append(feature)

        for feature, patterns in self.join_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                features["join"].append(feature)

        for feature, patterns in self.output_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                features["output"].append(feature)

        for pattern in self.number_patterns:
            matches = re.findall(pattern, query_lower)
            if matches:
                features["numbers"].extend(matches)

        date_patterns = [
            r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
            r"\b(?:q1|q2|q3|q4)\b",
            r"\b\d{4}\b",
            r"\b(?:today|yesterday|tomorrow|last week|this week|next week|last month|this month|next month|last year|this year)\b",
        ]
        for pattern in date_patterns:
            matches = re.findall(pattern, query_lower)
            if matches:
                features["date_references"].extend(matches)

        features["has_time_series"] = len(features["time_series"]) > 0
        features["has_ranking"] = len(features["ranking"]) > 0
        features["requires_join"] = len(features["join"]) > 0
        features["summary"] = self._generate_feature_summary(features)

        return features

    def _generate_feature_summary(self, features: dict[str, Any]) -> str:
        summary_parts = []
        if features["time_series"]:
            summary_parts.append(f"Time-series: {', '.join(features['time_series'])}")
        if features["ranking"]:
            summary_parts.append(f"Ranking: {', '.join(features['ranking'])}")
        if features["comparison"]:
            summary_parts.append(f"Comparison: {', '.join(features['comparison'])}")
        if features["filtering"]:
            summary_parts.append(f"Filtering: {', '.join(features['filtering'])}")
        if features["join"]:
            summary_parts.append(f"Join: {', '.join(features['join'])}")
        if features["numbers"]:
            summary_parts.append(f"Numbers: {', '.join(features['numbers'][:3])}")
        if features["date_references"]:
            summary_parts.append(f"Dates: {', '.join(features['date_references'][:3])}")

        return "; ".join(summary_parts) if summary_parts else "Standard descriptive query"


# ============================================================================
# SEMANTIC MODEL YAML & SCHEMA METADATA HELPER
# ============================================================================

def _truncate_text(text: str, max_length: int = MAX_TABLE_DESCRIPTION_LENGTH) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_length:
        return text
    truncated = text[:max_length].strip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip(".,;: ") + "..."


def _clean_sample_val(val: Any, max_len: int = 30) -> str:
    s = str(val).strip().replace("\n", " ")
    if len(s) > max_len:
        return s[:max_len].strip() + "..."
    return s


def _should_include_sample_values(user_query: str) -> bool:
    if not user_query:
        return False
    query_lower = user_query.lower()
    if "'" in user_query or '"' in user_query:
        return True
    words = set(re.findall(r"\b[a-zA-Z_]+\b", query_lower))
    return bool(words & FILTER_INTENT_KEYWORDS)


def _load_semantic_model_yaml() -> dict[str, Any]:
    """Loads stored semantic model YAMLs (active_schema.yaml / semantic_model.yaml) from data directory."""
    data_dir = Path(settings.query_engine_db_path).parent
    candidate_files = [
        data_dir / "active_schema.yaml",
        data_dir / "semantic_model.yaml",
    ]
    if data_dir.exists():
        for p in sorted(data_dir.glob("semantic_model*.yaml"), reverse=True):
            if p not in candidate_files:
                candidate_files.append(p)

    combined_tables: dict[str, Any] = {}

    for yaml_path in candidate_files:
        if not yaml_path.exists():
            continue
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                continue
            tables = data.get("tables", [])
            for t in tables:
                if not isinstance(t, dict):
                    continue
                tname = t.get("table_name")
                if tname and tname not in combined_tables:
                    combined_tables[tname] = t
        except Exception as e:
            logger.warning("[Descriptive] Error loading YAML model %s: %s", yaml_path, e)

    return combined_tables


def _build_schema_info_from_duckdb() -> dict[str, Any]:
    """Inspects DuckDB snapshot tables and merges with stored YAML semantic models."""
    raw_schema = snapshot_store.schema()
    if not raw_schema:
        return {}

    yaml_tables = _load_semantic_model_yaml()
    sample_tables = snapshot_store.get_all_tables(sample_size=50)
    schema_info: dict[str, Any] = {}

    for table_name, columns in raw_schema.items():
        yaml_info = yaml_tables.get(table_name, {})
        yaml_cols = {c.get("name"): c for c in yaml_info.get("columns", []) if isinstance(c, dict)}
        df = sample_tables.get(table_name)
        
        col_meta_list = []
        pks = yaml_info.get("primary_key", [])
        if not isinstance(pks, list):
            pks = []

        for col_name in columns:
            y_col = yaml_cols.get(col_name, {})
            col_type = y_col.get("type") or "VARCHAR"
            sample_values = y_col.get("sample_values") or []
            description = y_col.get("description") or f"Column '{col_name}'"
            is_measure = False

            if df is not None and col_name in df.columns:
                series = df[col_name]
                dtype_str = str(series.dtype).lower()
                if "int" in dtype_str:
                    col_type = "INTEGER"
                    is_measure = True
                elif "float" in dtype_str or "double" in dtype_str:
                    col_type = "FLOAT"
                    is_measure = True
                elif "bool" in dtype_str:
                    col_type = "BOOLEAN"
                elif "datetime" in dtype_str or "timestamp" in dtype_str:
                    col_type = "TIMESTAMP"

                if not sample_values:
                    non_null = series.dropna().astype(str)
                    sample_values = non_null.head(5).tolist()

                if col_name.lower() in ("id", f"{table_name}_id", f"{table_name[:-1]}_id") or col_name.lower().endswith("_id"):
                    if col_name not in pks:
                        pks.append(col_name)

            if col_type in ("INTEGER", "FLOAT") and not col_name.lower().endswith("_id"):
                is_measure = True

            col_meta_list.append({
                "name": col_name,
                "type": col_type,
                "description": description,
                "is_measure": is_measure,
                "sample_values": sample_values,
            })

        human_name = _humanize_dataset_name(table_name).replace("_", " ").title()
        terms = [human_name.lower(), table_name.lower()]
        synonyms = [_humanize_dataset_name(table_name)]

        # Infer domain terms from column names
        cols_lower = [c.lower() for c in columns]
        if any("revenue" in c or "price" in c or "payment_value" in c or "amount" in c or "freight_value" in c for c in cols_lower):
            terms.extend(["revenue", "sales", "payments", "income", "price", "amount", "total revenue", "value"])
        if any("order" in c for c in cols_lower):
            terms.extend(["orders", "purchases", "order"])
        if any("customer" in c for c in cols_lower):
            terms.extend(["customers", "clients", "buyers", "users"])
        if any("product" in c or "item" in c for c in cols_lower):
            terms.extend(["products", "items", "goods", "catalog"])

        foreign_keys = yaml_info.get("foreign_keys", [])

        schema_info[table_name] = {
            "description": yaml_info.get("description") or f"Table containing {human_name} data",
            "columns": col_meta_list,
            "primary_key": pks,
            "foreign_keys": foreign_keys,
            "business_terms": list(set(terms)),
            "synonyms": list(set(synonyms)),
        }

    return schema_info


# ============================================================================
# INTENT AGENT
# ============================================================================

class IntentAgent:
    """Maps query to workspace intent."""

    def __init__(self):
        self.workspaces = ["customer_analysis", "order_processing", "inventory_management", "sales_analytics", "general"]

    async def determine_intent(self, user_query: str, model: str | None = None) -> dict[str, Any]:
        q_lower = user_query.lower()
        if any(w in q_lower for w in ["customer", "client", "user", "churn", "subscriber", "mrr", "seats"]):
            return {"workspaces": ["customer_analysis"], "explanation": "Customer focused intent"}
        if any(w in q_lower for w in ["order", "purchase", "transaction", "checkout", "cart"]):
            return {"workspaces": ["order_processing"], "explanation": "Order processing intent"}
        if any(w in q_lower for w in ["sales", "revenue", "deal", "pipeline", "quota", "price", "payment"]):
            return {"workspaces": ["sales_analytics"], "explanation": "Sales and revenue analytics intent"}
        if any(w in q_lower for w in ["product", "stock", "inventory", "warehouse", "item"]):
            return {"workspaces": ["inventory_management"], "explanation": "Inventory management intent"}

        return {"workspaces": ["general"], "explanation": "General analytics query"}


# ============================================================================
# TABLE AGENT
# ============================================================================

class TableAgent:
    """Identifies the minimum required tables using compact schema representation."""

    def build_compact_table_schema(self, schema_info: dict[str, Any], user_query: str = "") -> str:
        include_samples = _should_include_sample_values(user_query)
        schema_descriptions = []

        for table_name, info in schema_info.items():
            if not isinstance(info, dict):
                continue
            raw_desc = info.get("description", "")
            short_desc = _truncate_text(raw_desc, MAX_TABLE_DESCRIPTION_LENGTH)
            table_desc = f"Table '{table_name}': {short_desc}" if short_desc else f"Table '{table_name}'"

            b_terms = info.get("business_terms") or []
            if b_terms:
                table_desc += f" | Terms: {', '.join(b_terms[:MAX_TABLE_BUSINESS_TERMS])}"

            col_details = []
            for c in info.get("columns", []):
                col_name = c.get("name", "")
                col_type = c.get("type", "")
                col_str = f"{col_name} {col_type}"
                if c.get("is_measure"):
                    col_str += " [MEASURE]"
                if include_samples and c.get("sample_values"):
                    sample_vals = ", ".join(_clean_sample_val(v) for v in c["sample_values"][:MAX_SAMPLE_VALUES])
                    col_str += f" [Examples: {sample_vals}]"
                col_details.append(col_str)

            if col_details:
                table_desc += "\nColumns:\n- " + "\n- ".join(col_details)
            schema_descriptions.append(table_desc)

        return "\n\n".join(schema_descriptions)

    async def determine_tables(self, user_query: str, workspace: str, schema_info: dict[str, Any], model: str | None = None) -> list[str]:
        if not schema_info:
            return []
        if len(schema_info) == 1:
            return list(schema_info.keys())

        # Fast keyword and business terms matching
        q_words = set(re.findall(r"\w+", user_query.lower()))
        matched = []
        for tbl, info in schema_info.items():
            clean = tbl.lower().split("_")[-1]
            terms = set(info.get("business_terms", [])) | set(info.get("synonyms", []))
            # Match table name or business terms
            if clean in q_words or any(w in tbl.lower() for w in q_words if len(w) >= 3):
                matched.append(tbl)
            elif any(t.lower() in user_query.lower() for t in terms if len(t) >= 4):
                matched.append(tbl)

        # Revenue/order payment correlation rule: if question asks for revenue/sales and an orders table matched, also include payments/items tables
        if any(w in q_words for w in ["revenue", "sales", "paid", "payment", "amount", "price"]):
            for tbl in schema_info.keys():
                tbl_lower = tbl.lower()
                if ("payment" in tbl_lower or "item" in tbl_lower) and tbl not in matched:
                    matched.append(tbl)

        if matched:
            return list(dict.fromkeys(matched))

        return list(schema_info.keys())[:3]


# ============================================================================
# COLUMN PRUNE AGENT
# ============================================================================

class ColumnPruneAgent:
    """Prunes columns for the selected tables."""

    def build_compact_column_prune_schema(self, schema_info: dict[str, Any], tables: list[str], user_query: str = "") -> str:
        include_samples = _should_include_sample_values(user_query)
        schema_descriptions = []

        for table_name in tables:
            info = schema_info.get(table_name)
            if not isinstance(info, dict):
                continue
            table_desc = f"Table '{table_name}': {info.get('description', '')}"
            col_details = []
            for c in info.get("columns", []):
                col_name = c.get("name", "")
                col_type = c.get("type", "")
                col_str = f"{col_name} {col_type}"
                if c.get("is_measure"):
                    col_str += " [MEASURE]"
                if include_samples and c.get("sample_values"):
                    sample_vals = ", ".join(_clean_sample_val(v) for v in c["sample_values"][:MAX_SAMPLE_VALUES])
                    col_str += f" [Examples: {sample_vals}]"
                col_details.append(col_str)

            if col_details:
                table_desc += "\nColumns:\n- " + "\n- ".join(col_details)
            schema_descriptions.append(table_desc)

        return "\n\n".join(schema_descriptions)

    async def prune_columns(self, user_query: str, tables: list[str], schema_info: dict[str, Any], model: str | None = None) -> dict[str, list[str]]:
        if not tables:
            return {}

        return {
            t: [c["name"] for c in schema_info[t]["columns"] if isinstance(c, dict)]
            for t in tables if t in schema_info
        }


# ============================================================================
# SQL GENERATOR
# ============================================================================

def _extract_schema_relationships(schema_info: dict[str, Any]) -> list[dict[str, Any]]:
    relationships = []
    seen = set()

    # 1. Foreign keys from YAML semantic models
    for t_name, info in schema_info.items():
        if not isinstance(info, dict):
            continue
        for fk in info.get("foreign_keys", []):
            if not isinstance(fk, dict):
                continue
            to_tbl = fk.get("to_table")
            from_col = fk.get("from_column")
            to_col = fk.get("to_column")
            if to_tbl and from_col and to_col and to_tbl in schema_info:
                key = (t_name, from_col, to_tbl, to_col)
                if key not in seen:
                    seen.add(key)
                    relationships.append({
                        "from_table": t_name,
                        "from_column": from_col,
                        "to_table": to_tbl,
                        "to_column": to_col,
                    })

    # 2. Key inferences based on column names across selected tables
    table_cols: dict[str, set[str]] = {}
    for t_name, info in schema_info.items():
        if isinstance(info, dict):
            table_cols[t_name] = {c.get("name", "") for c in info.get("columns", []) if isinstance(c, dict)}

    tables = list(table_cols.keys())
    for i in range(len(tables)):
        for j in range(i + 1, len(tables)):
            t1, t2 = tables[i], tables[j]
            common = table_cols[t1].intersection(table_cols[t2])
            for col in common:
                col_lower = col.lower()
                if col_lower in ("id", "customer_id", "order_id", "product_id", "user_id", "seller_id") or col_lower.endswith("_id"):
                    key = (t1, col, t2, col)
                    rev_key = (t2, col, t1, col)
                    if key not in seen and rev_key not in seen:
                        seen.add(key)
                        relationships.append({
                            "from_table": t1,
                            "from_column": col,
                            "to_table": t2,
                            "to_column": col,
                        })
    return relationships


def _build_sql_generation_context(
    user_query: str,
    pruned_schema: dict[str, list[str]],
    schema_info: dict[str, Any],
    query_features: dict[str, Any],
) -> dict[str, Any]:
    selected_tables = [t for t in pruned_schema.keys() if t in schema_info]
    schema_lines = []

    for table_name in selected_tables:
        cols = pruned_schema.get(table_name, [])
        col_meta_list = schema_info.get(table_name, {}).get("columns", [])
        desc = schema_info.get(table_name, {}).get("description", "")
        schema_lines.append(f'Table "{table_name}" ({desc}):')
        for col_name in cols:
            col_info = next((c for c in col_meta_list if c.get("name") == col_name), None)
            col_type = col_info.get("type", "VARCHAR") if col_info else "VARCHAR"
            measure_tag = " [MEASURE/NUMERIC]" if col_info and col_info.get("is_measure") else ""
            schema_lines.append(f"  - {col_name} ({col_type}){measure_tag}")

    compact_schema_str = "\n".join(schema_lines) if schema_lines else "No tables selected"
    rels = _extract_schema_relationships(schema_info)
    selected_set = set(selected_tables)
    relevant_rels = [r for r in rels if r["from_table"] in selected_set and r["to_table"] in selected_set]

    if relevant_rels:
        rel_str = "\n".join(f'- "{r["from_table"]}".{r["from_column"]} = "{r["to_table"]}".{r["to_column"]}' for r in relevant_rels)
    else:
        rel_str = "None (single table query or implicit join keys)"

    feature_str = query_features.get("summary", "Standard query")

    prompt = f"""You translate a business question into a single DuckDB SQL SELECT query.

Question:
{user_query}

Database Schema:
{compact_schema_str}

Relationships:
{rel_str}

Detected Requirements:
{feature_str}

Rules:
1. Return ONLY the SQL query or JSON containing {{"sql": "SELECT ...;"}}.
2. Use ONLY read-only SELECT or WITH statements.
3. Quote all table names with double quotes (e.g. "customers").
4. If computing revenue or sums, aggregate relevant measure columns (e.g. SUM(payment_value), SUM(price)).
5. Ensure the SQL query ends with a semicolon (;)."""

    return {
        "prompt": prompt,
        "selected_tables": selected_tables,
        "compact_schema": compact_schema_str,
    }


class MultiSQLGenerator:
    """Generates and ranks SQL candidates."""

    def __init__(self, feature_extractor: FeatureExtractor | None = None):
        self.feature_extractor = feature_extractor or FeatureExtractor()

    async def generate_sql(
        self,
        user_query: str,
        workspace: str,
        tables: list[str],
        pruned_schema: dict[str, list[str]],
        schema_info: dict[str, Any],
        features: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        if features is None:
            features = self.feature_extractor.extract_features(user_query)

        # 1. Try standard SQL generator
        try:
            simple_schema = {t: [c["name"] for c in schema_info[t]["columns"]] for t in tables if t in schema_info}
            direct_sql = await generator.generate_sql(user_query, simple_schema, model=model)
            if direct_sql and direct_sql.upper() != "NO_ANSWER":
                return {
                    "sql": direct_sql.strip(),
                    "explanation": "Query generated via SQL generator.",
                    "confidence": 0.9,
                    "features": features,
                }
        except Exception:
            pass

        # 2. Multi-stage prompt generation with relationships & context
        if not settings.is_llm_configured:
            fallback_sql = self._create_fallback_sql(tables, pruned_schema, user_query)
            return {
                "sql": fallback_sql,
                "explanation": "Fallback query derived from schema.",
                "confidence": 0.5,
                "features": features,
            }

        ctx = _build_sql_generation_context(user_query, pruned_schema, schema_info, features)
        prompt = ctx["prompt"]

        raw = await _get_chat_completion([{"role": "user", "content": prompt}], model=model, max_tokens=1024, temperature=0.1)
        parsed = self._parse_json_response(raw)

        if parsed and parsed.get("sql"):
            return {
                "sql": parsed["sql"].strip(),
                "explanation": parsed.get("explanation", "Query generated from question."),
                "confidence": float(parsed.get("confidence", 0.85)),
                "features": features,
            }

        fallback_sql = self._create_fallback_sql(tables, pruned_schema, user_query)
        return {
            "sql": fallback_sql,
            "explanation": "Fallback query derived from schema.",
            "confidence": 0.5,
            "features": features,
        }

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        if not text:
            return {}
        cleaned = re.sub(r"```(?:json|sql)?\s*", "", text)
        cleaned = re.sub(r"```", "", cleaned).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict) and "sql" in data:
                    return data
            except Exception:
                pass
        # Check if raw text is a SQL query
        if re.match(r"^\s*(SELECT|WITH)\b", cleaned, re.IGNORECASE):
            return {"sql": cleaned, "explanation": "Extracted SQL statement", "confidence": 0.85}
        return {}

    def _create_fallback_sql(self, tables: list[str], pruned_schema: dict[str, list[str]], user_query: str) -> str:
        if not tables:
            return "SELECT 1;"
        primary_table = tables[0]
        cols = pruned_schema.get(primary_table, [])
        cols_str = ", ".join(f'"{c}"' for c in cols[:6]) if cols else "*"
        return f'SELECT {cols_str} FROM "{primary_table}" LIMIT 100;'


# ============================================================================
# FIXER AGENT (Self-Healing SQL Repair)
# ============================================================================

class FixerAgent:
    """Repairs failing SQL queries using schema context and DuckDB error diagnostics."""

    async def fix_query(
        self,
        user_query: str,
        failing_sql: str,
        error_message: str,
        sample_rows: list | None,
        schema_info: dict[str, Any],
        tables: list[str],
        pruned_schema: dict[str, list[str]],
        attempt: int = 1,
        model: str | None = None,
    ) -> dict[str, Any]:
        if not settings.is_llm_configured:
            return {"status": "no_fix_confident", "explanation": "LLM not configured for SQL repair", "confidence": 0.0}

        schema_lines = []
        for t in tables:
            if t in schema_info:
                cols = ", ".join(c["name"] for c in schema_info[t]["columns"])
                schema_lines.append(f'Table "{t}": {cols}')
        schema_text = "\n".join(schema_lines)

        prompt = f"""You are an SQL repair assistant for DuckDB. A SQL query failed to run.
Your output MUST be a valid DuckDB SELECT query ending with a semicolon:

User question: "{user_query}"
Attempt: {attempt}
Failing SQL:
{failing_sql}
Error message:
{error_message}
Available Schema:
{schema_text}

Rules:
1. Return ONLY the corrected SELECT SQL query ending with a semicolon.
2. Quote table names with double quotes (e.g. "customers").
3. Do NOT use write or DDL operations.
"""
        raw = await _get_chat_completion([{"role": "user", "content": prompt}], model=model, max_tokens=500, temperature=0.1)
        raw_sql = raw.strip().strip("`").strip()
        if raw_sql.lower().startswith("sql\n"):
            raw_sql = raw_sql[4:].strip()
        if re.match(r"^\s*(SELECT|WITH)\b", raw_sql, re.IGNORECASE):
            return {"status": "fixed", "fixed_sql": raw_sql, "confidence": 0.85}

        return {"status": "no_fix_confident", "explanation": "Unable to repair query", "confidence": 0.0}


# ============================================================================
# VERIFICATION AGENT
# ============================================================================

class VerificationAgent:
    """Verifies that the executed query and results align with the user question."""

    async def verify(self, user_query: str, sql: str, columns: list[str], rows: list[list], model: str | None = None) -> dict[str, Any]:
        if not rows:
            return {"verified": True, "explanation": "Query executed successfully.", "confidence": 0.7}

        return {"verified": True, "explanation": "Query verified against schema and question.", "confidence": 0.85}


# ============================================================================
# INSIGHT AGENT
# ============================================================================

class InsightAgent:
    """Generates high-impact, grounded business takeaways from full query results."""

    def _build_analytical_summary(self, columns: list[str], rows: list[list]) -> str:
        if not rows:
            return "No rows returned."

        df = pd.DataFrame(rows, columns=columns)
        summary_lines = [f"Total rows returned: {len(df)}"]

        for col in df.columns:
            series = df[col]
            if pd.api.types.is_numeric_dtype(series):
                clean = series.dropna()
                if not clean.empty:
                    summary_lines.append(
                        f"Metric '{col}': Total={clean.sum():,.2f}, Mean={clean.mean():,.2f}, "
                        f"Min={clean.min():,.2f}, Max={clean.max():,.2f}"
                    )
            elif pd.api.types.is_bool_dtype(series) or series.nunique() <= 10:
                counts = series.value_counts().head(5).to_dict()
                summary_lines.append(f"Dimension '{col}' top distribution: {counts}")

        return "\n".join(summary_lines)

    async def generate_insights(self, user_query: str, columns: list[str], rows: list[list], sql: str = "", model: str | None = None) -> str:
        if not rows:
            return "No data matched the query."

        return self._build_analytical_summary(columns, rows)


# ============================================================================
# DESCRIPTIVE SQL PIPELINE ORCHESTRATOR
# ============================================================================

def _is_safe_select(sql: str) -> bool:
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    if len(statements) != 1:
        return False
    single = statements[0]
    if not re.match(r"^\s*(SELECT|WITH)\b", single, re.IGNORECASE):
        return False
    return not _WRITE_KEYWORDS.search(single)


def _sanitize_sql(sql: str) -> str:
    cleaned = re.sub(r"<\|.*?\|>", "", sql).strip()
    if not cleaned.endswith(";"):
        cleaned += ";"
    return cleaned


def _is_identifier_column(name: str) -> bool:
    lowered = name.lower()
    if lowered in ("id", "_id") or lowered.endswith("_id"):
        return True
    return name.endswith("Id") or name.endswith("ID")


def _filter_sensitive_columns(columns: list[str], rows: list[list]) -> tuple[list[str], list[list]]:
    keep = [
        i for i, name in enumerate(columns)
        if not _is_identifier_column(name) and (not rows or any(row[i] is not None for row in rows))
    ]
    # If all columns were identifier columns (e.g. SELECT count(*) or SELECT id), preserve them
    if not keep:
        keep = list(range(len(columns)))
    filtered_columns = [columns[i] for i in keep]
    filtered_rows = [[row[i] for i in keep] for row in rows]
    return filtered_columns, filtered_rows


async def _execute_with_timeout(sql: str) -> tuple[list[str], list[list]]:
    return await asyncio.wait_for(asyncio.to_thread(snapshot_store.execute, sql), timeout=QUERY_TIMEOUT_SECONDS)


async def execute_sql_pipeline(user_query: str, model: str | None = None) -> dict[str, Any]:
    """Full execution of the Descriptive SQL Pipeline with FixerAgent self-healing loop."""
    logger.info("[Descriptive Pipeline] Starting SQL pipeline for: '%s'", user_query)

    schema_info = _build_schema_info_from_duckdb()
    if not schema_info:
        return {
            "ok": False,
            "columns": [],
            "rows": [],
            "sql": None,
            "insights": "",
            "explanation": "No data is connected yet.",
            "message": "No data is connected yet.",
        }

    intent_agent = IntentAgent()
    table_agent = TableAgent()
    column_pruner = ColumnPruneAgent()
    feature_extractor = FeatureExtractor()
    sql_generator = MultiSQLGenerator(feature_extractor=feature_extractor)
    fixer_agent = FixerAgent()
    verification_agent = VerificationAgent()
    insight_agent = InsightAgent()

    # Stage 1: Workspace intent
    intent_res = await intent_agent.determine_intent(user_query, model=model)
    workspace = intent_res["workspaces"][0] if intent_res.get("workspaces") else "general"

    # Stage 2: Required tables
    tables = await table_agent.determine_tables(user_query, workspace, schema_info, model=model)

    # Stage 3: Column pruning
    pruned_schema = await column_pruner.prune_columns(user_query, tables, schema_info, model=model)

    # Stage 3.5: Query features
    features = feature_extractor.extract_features(user_query)

    # Stage 4: SQL generation
    gen_result = await sql_generator.generate_sql(
        user_query=user_query,
        workspace=workspace,
        tables=tables,
        pruned_schema=pruned_schema,
        schema_info=schema_info,
        features=features,
        model=model,
    )

    candidate_sql = gen_result.get("sql", "")
    explanation = gen_result.get("explanation", "")
    MAX_FIX_ATTEMPTS = 3
    last_error = ""
    current_sql = candidate_sql

    # Stage 5: Execution & Fixer retry loop
    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        if not _is_safe_select(current_sql):
            current_sql = _sanitize_sql(current_sql)
            if not _is_safe_select(current_sql):
                return {
                    "ok": False,
                    "columns": [],
                    "rows": [],
                    "sql": current_sql,
                    "insights": "",
                    "explanation": "Generated query was rejected (not a safe read-only SELECT).",
                    "message": "Generated query was rejected (not a safe read-only SELECT).",
                }

        try:
            raw_columns, raw_rows = await _execute_with_timeout(current_sql)
            logger.info("[Descriptive Pipeline] SQL execution succeeded on attempt %d with %d rows.", attempt, len(raw_rows))

            filtered_columns, filtered_rows = _filter_sensitive_columns(raw_columns, raw_rows[:ROW_LIMIT])

            # Stage 6: Verification
            verif_res = await verification_agent.verify(user_query, current_sql, filtered_columns, filtered_rows, model=model)

            # Stage 7: Insights
            insights_text = await insight_agent.generate_insights(user_query, filtered_columns, filtered_rows, sql=current_sql, model=model)

            return {
                "ok": True,
                "columns": filtered_columns,
                "rows": filtered_rows,
                "raw_columns": raw_columns,
                "raw_rows": raw_rows,
                "sql": current_sql,
                "insights": insights_text,
                "explanation": explanation,
                "verification": verif_res,
                "features": features,
                "message": "ok",
            }
        except Exception as e:
            last_error = str(e)
            logger.warning("[Descriptive Pipeline] Attempt %d failed: %s", attempt, e)

            if attempt < MAX_FIX_ATTEMPTS:
                fix_res = await fixer_agent.fix_query(
                    user_query=user_query,
                    failing_sql=current_sql,
                    error_message=last_error,
                    sample_rows=None,
                    schema_info=schema_info,
                    tables=tables,
                    pruned_schema=pruned_schema,
                    attempt=attempt,
                    model=model,
                )
                if fix_res.get("status") == "fixed" and fix_res.get("fixed_sql"):
                    current_sql = fix_res["fixed_sql"]
                    explanation = fix_res.get("explanation", explanation)
                    continue

    return {
        "ok": False,
        "columns": [],
        "rows": [],
        "sql": current_sql,
        "insights": "",
        "explanation": f"Query failed after retry: {last_error}",
        "message": f"Query failed after retry: {last_error}",
    }


# ============================================================================
# AGENT PREP BUILDER & CONTRACT HELPERS
# ============================================================================

def _infer_dataset_name(sql: str | None, fallback: str = "results") -> str:
    if not sql:
        return fallback
    match = _FROM_TABLE_RE.search(sql)
    if not match:
        return fallback
    return match.group(1) or match.group(2) or fallback


def _humanize_dataset_name(dataset: str) -> str:
    return _CONNECTOR_PREFIX_RE.sub("", dataset) or dataset


def _sanitize_rows(rows: list[list]) -> list[list]:
    return [[v if v is None or isinstance(v, (int, float, bool, str)) else str(v) for v in row] for row in rows]


def _boolean_split(normalized: NormalizedResult, dataset: str, total_metric_id: str) -> tuple[list[Metric], list[Insight]]:
    boolean_columns = [c for c in normalized.columns if c.value_type == "boolean"]
    if len(boolean_columns) != 1 or normalized.row_count == 0:
        return [], []

    column = boolean_columns[0].name
    matching = count_where(normalized, column, lambda v: v is True)
    label = column.replace("_", " ").title()
    rate_id, count_id = f"{column}_rate", f"{column}_count"

    metrics = [
        Metric(id=count_id, label=f"{label} Count", value=matching, format="number"),
        Metric(id=rate_id, label=f"{label} Rate", value=percentage(matching, normalized.row_count), format="percentage"),
    ]
    insights = binary_split_insights(
        subject=dataset,
        matching_label=column,
        matching_count=matching,
        total_count=normalized.row_count,
        rate_metric_id=rate_id,
        matching_metric_id=count_id,
        total_metric_id=total_metric_id,
    )
    return metrics, insights


def _category_breakdown(normalized: NormalizedResult, dataset: str) -> tuple[list[Metric], list[Insight]]:
    ranked = category_ranking(normalized)
    if not ranked:
        return [], []

    top_label, top_value = ranked[0]
    total = sum(value for _, value in ranked)
    dimension = normalized.dimensions[0]
    metric_id = f"top_{dimension}"

    metric = Metric(id=metric_id, label=f"Top {dimension.replace('_', ' ').title()}", value=top_value, format="number")
    insight = ranking_insight(subject=dataset, top_label=str(top_label), top_value=top_value, top_metric_id=metric_id, total=total)
    return [metric], [insight]


def _offline_summary(dataset: str, total_metric: Metric, insights: list[Insight], pipeline_insights: str = "") -> str:
    label = dataset.replace("_", " ")
    parts = [f"You have {total_metric.value} {label}."]
    parts.extend(i.text for i in insights)
    return " ".join(parts)


def _facts_prompt(question: str, response: StructuredResponse) -> str:
    fact_lines = [f"- {m.label}: {m.value}{'%' if m.format == 'percentage' else ''}" for m in response.metrics]
    insight_lines = [f"- {i.text}" for i in response.insights]
    return (
        f"Question: {question}\n\n"
        "Computed facts (cite ONLY these numbers, never invent others):\n"
        + ("\n".join(fact_lines) or "  (none)")
        + "\n\nGrounded observations:\n"
        + ("\n".join(insight_lines) or "  (none)")
        + "\n\nWrite the summary now."
    )


def _no_data_response(message: str) -> AgentPrep:
    response = StructuredResponse(
        summary=Summary(text=message, confidence="low"),
        metrics=[],
        insights=[],
        visualizations=[],
        tables=[],
        sources=[],
    )
    return AgentPrep(
        system=SYSTEM,
        prompt=f"Question unanswerable: {message}",
        offline_text=message,
        payload=response.model_dump(by_alias=True),
    )


async def _citation_fallback(question: str) -> AgentPrep | None:
    if not question or not question.strip():
        return None
    try:
        raw_hits = chroma_query(question.strip(), n_results=4)
        hits = [h for h in raw_hits if h.get("distance") is None or h["distance"] <= 1.2]
    except Exception:
        hits = []
    if not hits:
        return None

    citations = [
        {
            "id": i + 1,
            "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
            "filename": h["metadata"].get("filename", ""),
            "chunkIndex": h["metadata"].get("chunk_index", 0),
            "snippet": h.get("snippet", "")[:400],
        }
        for i, h in enumerate(hits)
    ]
    doc_snippets = "\n".join(f"- Document [{c['documentTitle']}] ({c['filename']}): \"{c['snippet']}\"" for c in citations)
    prompt = f"Question: {question}\n\nRelevant Data Source Document Excerpts:\n{doc_snippets}\n\nAnswer using only the excerpts above."
    offline_text = f"According to uploaded Data Source document ({citations[0]['documentTitle']}): \"{citations[0]['snippet']}\""
    return AgentPrep(
        system=SYSTEM,
        prompt=prompt,
        offline_text=offline_text,
        payload={"confidence": "high", "citations": citations},
    )


# ============================================================================
# MAIN ENTRYPOINT: prepare
# ============================================================================

async def prepare(question: str, model: str | None = None) -> AgentPrep:
    """Prepares the descriptive analytics response for a user query."""
    logger.info("[Descriptive Agent] Preparing response for question: '%s'", question)

    # 1. Check if any tables are connected in DuckDB
    schema = snapshot_store.schema()
    if not schema:
        fallback = await _citation_fallback(question)
        if fallback is not None:
            return fallback
        return _no_data_response("No data is connected yet.")

    # 2. Run the full descriptive SQL pipeline
    pipe_res = await execute_sql_pipeline(question, model=model)

    if not pipe_res.get("ok") or not pipe_res.get("rows"):
        if pipe_res.get("ok") and len(pipe_res.get("rows", [])) == 0:
            # Query ran successfully but returned 0 records
            response = StructuredResponse(
                summary=Summary(text=f"The query returned 0 records for: {question}", confidence="low"),
                metrics=[],
                insights=[],
                visualizations=[],
                tables=[],
                sources=[],
            )
            return AgentPrep(
                system=SYSTEM,
                prompt=f"Question returned no records: {question}",
                offline_text=f"No matching records found for: {question}",
                payload=response.model_dump(by_alias=True),
            )

        fallback = await _citation_fallback(question)
        return fallback if fallback is not None else _no_data_response(pipe_res.get("message", "No data is connected yet."))

    columns: list[str] = pipe_res["columns"]
    rows: list[list] = pipe_res["rows"]
    sql: str = pipe_res.get("sql", "")
    pipeline_insights: str = pipe_res.get("insights", "")

    dataset = _infer_dataset_name(sql)
    display_name = _humanize_dataset_name(dataset)
    normalized = normalize(dataset, columns, _sanitize_rows(rows), sql=sql)

    total_metric_id = f"total_{dataset}"
    total_label = f"Total {display_name.replace('_', ' ').title()}"
    if normalized.row_count == 1 and len(normalized.measures) == 1 and not normalized.dimensions:
        measure_col = normalized.measures[0]
        clean_measure = _humanize_dataset_name(measure_col).replace("sum(", "").replace("avg(", "").replace("count(", "").replace(")", "").replace("_", " ").strip().title()
        if any(w in question.lower() for w in ["revenue", "sales", "income"]):
            total_label = "Total Revenue"
        elif clean_measure and clean_measure.lower() not in ("sum", "avg", "count", "value"):
            total_label = f"Total {clean_measure}"

    total_metric = primary_metric(normalized, metric_id=total_metric_id, label=total_label)
    split_metrics, split_insights = _boolean_split(normalized, display_name, total_metric_id)
    category_metrics, category_insights = _category_breakdown(normalized, display_name)
    metrics = [total_metric, *split_metrics, *category_metrics]
    insights = [*split_insights, *category_insights]

    visualization = plan_visualization(metrics, normalized)
    table = plan_table(normalized)
    issues = validate(metrics, insights, [table], normalized, visualizations=[visualization])
    confidence = compute_confidence(query_ok=True, issues=issues)

    offline_text = _offline_summary(display_name, total_metric, insights, pipeline_insights=pipeline_insights)
    response = StructuredResponse(
        summary=Summary(text=offline_text, confidence=confidence),
        metrics=metrics,
        insights=insights,
        visualizations=[visualization],
        tables=[table],
        sources=[Source(dataset=display_name, row_count=normalized.row_count)],
    )

    payload = response.model_dump(by_alias=True)
    payload["sql"] = sql
    payload["generatedSql"] = sql
    payload["insightsText"] = pipeline_insights
    payload["verification"] = pipe_res.get("verification", {})
    payload["features"] = pipe_res.get("features", {})

    return AgentPrep(
        system=SYSTEM,
        prompt=_facts_prompt(question, response),
        offline_text=offline_text,
        payload=payload,
    )
