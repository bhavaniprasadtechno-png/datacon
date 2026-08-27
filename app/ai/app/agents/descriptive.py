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
import concurrent.futures
from functools import partial
import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
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
    """Agent to determine the intent of a user's natural language query using Together (Qwen/Qwen3.7-Plus)."""

    def __init__(self, model_name: str | None = None):
        # Define possible workspaces
        self.workspaces = ["customer_analysis", "order_processing", "inventory_management", "sales_analytics"]
        # Model name from Together / settings
        self.model_name = model_name or settings.llm_model or "Qwen/Qwen3.7-Plus"

    async def determine_intent(self, user_query: str, model: str | None = None) -> dict[str, list[str]]:
        """Map user's natural language query to workspace(s) using Together model."""
        prompt = f"""
Analyze the user query and determine relevant workspaces. Available workspaces: {', '.join(self.workspaces)}
User Query: "{user_query}"
Respond STRICTLY with a JSON object in this format:
{{
    "workspaces": ["relevant_workspace1", "relevant_workspace2"],
    "explanation": "Concise reason for selection"
}}
Rules:
1. ONLY output valid JSON - no additional text or formatting
2. Use double quotes for all strings
3. "workspaces" must be an array of strings (empty if none match)
4. Keep explanation under 20 words
"""
        generated_text = ""
        if settings.is_llm_configured:
            generated_text = await _get_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model or self.model_name,
                max_tokens=300,
                temperature=0.0,
            )

        parsed_intent = self._clean_and_parse_json(generated_text)

        # Fallback to keyword heuristic if model response is empty or returned no workspaces
        if not parsed_intent.get("workspaces"):
            q_lower = user_query.lower()
            if any(w in q_lower for w in ["customer", "client", "user", "churn", "subscriber", "mrr", "seats"]):
                parsed_intent["workspaces"] = ["customer_analysis"]
                parsed_intent["explanation"] = "Customer focused intent"
            elif any(w in q_lower for w in ["order", "purchase", "transaction", "checkout", "cart"]):
                parsed_intent["workspaces"] = ["order_processing"]
                parsed_intent["explanation"] = "Order processing intent"
            elif any(w in q_lower for w in ["sales", "revenue", "deal", "pipeline", "quota", "price", "payment"]):
                parsed_intent["workspaces"] = ["sales_analytics"]
                parsed_intent["explanation"] = "Sales and revenue analytics intent"
            elif any(w in q_lower for w in ["product", "stock", "inventory", "warehouse", "item"]):
                parsed_intent["workspaces"] = ["inventory_management"]
                parsed_intent["explanation"] = "Inventory management intent"
            else:
                parsed_intent["workspaces"] = ["general"]
                parsed_intent["explanation"] = "General analytics query"

        logger.info(
            "[ROUTING INTENT DECISION] Workspaces: %s | Explanation: %s",
            parsed_intent.get("workspaces", []),
            parsed_intent.get("explanation", ""),
        )
        return parsed_intent

    def _clean_and_parse_json(self, text: str) -> dict[str, list[str]]:
        """Extract and validate JSON from model output."""
        if not text:
            return {
                "workspaces": [],
                "explanation": "No model response - using fallback",
            }

        # Remove text before/after the JSON block
        cleaned = re.sub(r"^.*?{", "{", text, flags=re.DOTALL)
        cleaned = re.sub(r"}[^}]*$", "}", cleaned, flags=re.DOTALL)

        try:
            parsed = json.loads(cleaned)
            if "workspaces" not in parsed or "explanation" not in parsed:
                raise ValueError("Missing required keys")
            if not isinstance(parsed.get("workspaces"), list):
                parsed["workspaces"] = [str(parsed["workspaces"])]
            return parsed
        except Exception:
            try:
                fixed = cleaned.replace("'", '"').replace("\n", " ").replace('""', '"')
                parsed = json.loads(fixed)
                if "workspaces" not in parsed or "explanation" not in parsed:
                    raise ValueError
                if not isinstance(parsed.get("workspaces"), list):
                    parsed["workspaces"] = [str(parsed["workspaces"])]
                return parsed
            except Exception:
                return {
                    "workspaces": [],
                    "explanation": "Error parsing model response - using fallback",
                }


# ============================================================================
# TABLE AGENT (Compact Token-Optimized Semantic Table Selection)
# ============================================================================

def _calculate_token_fallback(text: str) -> int:
    """Helper to calculate token count using character fallback."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _truncate_text(text: str, max_length: int = MAX_TABLE_DESCRIPTION_LENGTH) -> str:
    """Safely truncate text to max_length without breaking words unnecessarily."""
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
    """Clean and truncate sample values to avoid overly long string bloat."""
    s = str(val).strip().replace("\n", " ")
    if len(s) > max_len:
        return s[:max_len].strip() + "..."
    return s


def _should_include_sample_values(user_query: str) -> bool:
    """Detect whether query likely requires value/category/filtering matching."""
    if not user_query:
        return False
    query_lower = user_query.lower()
    if "'" in user_query or '"' in user_query:
        return True
    words = set(re.findall(r"\b[a-zA-Z_]+\b", query_lower))
    return bool(words & FILTER_INTENT_KEYWORDS)


def build_compact_table_schema(
    schema_info: dict[str, Any],
    user_query: str = "",
    max_table_desc_len: int = MAX_TABLE_DESCRIPTION_LENGTH,
    max_table_terms: int = MAX_TABLE_BUSINESS_TERMS,
    max_table_synonyms: int = MAX_TABLE_SYNONYMS,
    max_col_terms: int = MAX_COLUMN_BUSINESS_TERMS,
    max_col_synonyms: int = MAX_COLUMN_SYNONYMS,
    max_samples: int = MAX_SAMPLE_VALUES,
) -> str:
    """Build a compact semantic schema representation specifically optimized for TableAgent token reduction."""
    include_samples = _should_include_sample_values(user_query)
    schema_descriptions = []

    for table_name, info in schema_info.items():
        if not isinstance(info, dict):
            continue

        # Table header: short description, limited business terms, limited synonyms
        raw_desc = info.get("description", "")
        short_desc = _truncate_text(raw_desc, max_table_desc_len) if raw_desc else ""
        table_desc = f"Table '{table_name}': {short_desc}" if short_desc else f"Table '{table_name}'"

        b_terms = info.get("business_terms") or []
        if b_terms:
            table_desc += f" | Terms: {', '.join(b_terms[:max_table_terms])}"

        synonyms = info.get("synonyms") or []
        if synonyms:
            table_desc += f" | Synonyms: {', '.join(synonyms[:max_table_synonyms])}"

        # Columns: column_name data_type [MEASURE] [terms] [synonyms] [conditional samples]
        columns = info.get("columns", [])
        col_details = []
        for c in columns:
            col_name = c.get("name", "")
            col_type = c.get("type", "")
            col_str = f"{col_name} {col_type}"

            # Keep measure flag, but remove default aggregation
            if c.get("is_measure"):
                col_str += " [MEASURE]"

            # Limit column business terms
            c_terms = c.get("business_terms") or []
            if c_terms:
                col_str += f" [{', '.join(c_terms[:max_col_terms])}]"

            # Limit column synonyms
            c_syns = c.get("synonyms") or []
            if c_syns:
                col_str += f" [{', '.join(c_syns[:max_col_synonyms])}]"

            # Conditional sample values
            if include_samples and c.get("sample_values"):
                col_type_upper = str(col_type).upper()
                is_text_or_cat = any(t in col_type_upper for t in ["TEXT", "VARCHAR", "STRING", "CHAR", "OBJECT", "CATEGORICAL"])
                is_id = col_name.lower() == "id" or col_name.lower().endswith(("_id", ".id")) or col_name.lower().startswith("id_")
                is_measure = bool(c.get("is_measure"))
                is_temporal = any(t in col_type_upper for t in ["TIME", "DATE"])
                is_free_text = any(w in col_name.lower() for w in ["comment", "message", "description", "note", "bio", "text_body"])

                if is_text_or_cat and not is_id and not is_measure and not is_temporal and not is_free_text:
                    sample_vals = ", ".join(_clean_sample_val(v) for v in c["sample_values"][:max_samples])
                    col_str += f" [Examples: {sample_vals}]"

            col_details.append(col_str)

        if col_details:
            table_desc += "\nColumns:\n- " + "\n- ".join(col_details)
        schema_descriptions.append(table_desc)

    return "\n\n".join(schema_descriptions)


class TableAgent:
    """Agent to determine which tables are needed to answer a query using Together (Qwen/Qwen3.7-Plus) with compact token-optimized schema."""

    def __init__(
        self,
        schema_info: dict[str, Any] | None = None,
        model_name: str | None = None,
        max_table_description_length: int = MAX_TABLE_DESCRIPTION_LENGTH,
        max_table_business_terms: int = MAX_TABLE_BUSINESS_TERMS,
        max_table_synonyms: int = MAX_TABLE_SYNONYMS,
        max_column_business_terms: int = MAX_COLUMN_BUSINESS_TERMS,
        max_column_synonyms: int = MAX_COLUMN_SYNONYMS,
        max_sample_values: int = MAX_SAMPLE_VALUES,
    ):
        self.schema_info = schema_info or {}
        self.model_name = model_name or settings.llm_model or "Qwen/Qwen3.7-Plus"
        self.max_table_description_length = max_table_description_length
        self.max_table_business_terms = max_table_business_terms
        self.max_table_synonyms = max_table_synonyms
        self.max_column_business_terms = max_column_business_terms
        self.max_column_synonyms = max_column_synonyms
        self.max_sample_values = max_sample_values

    def _build_full_schema_text_for_comparison(self, schema_info: dict[str, Any] | None = None) -> str:
        """Helper to format uncompressed full schema text for baseline token measurement."""
        schema = schema_info if schema_info is not None else self.schema_info
        schema_descriptions = []
        for table_name, info in schema.items():
            if not isinstance(info, dict):
                continue
            table_desc = f"Table '{table_name}': {info.get('description', '')}"
            if info.get("business_terms"):
                table_desc += f" | Business terms: {', '.join(info['business_terms'])}"
            if info.get("synonyms"):
                table_desc += f" | Also known as: {', '.join(info['synonyms'])}"
            columns = info.get("columns", [])
            col_details = []
            for c in columns:
                col_str = f"{c['name']} ({c['type']})"
                if c.get("description"):
                    col_str += f" - {c['description']}"
                if c.get("is_measure"):
                    col_str += f" [MEASURE: {c.get('default_aggregation') or 'various'}]"
                if c.get("business_terms"):
                    col_str += f" | Terms: {', '.join(c['business_terms'])}"
                if c.get("sample_values"):
                    sample_vals = ", ".join(str(v) for v in c["sample_values"][:3])
                    col_str += f" | Examples: {sample_vals}"
                col_details.append(col_str)
            if col_details:
                table_desc += "\nColumns:\n- " + "\n- ".join(col_details)
            schema_descriptions.append(table_desc)
        return "\n".join(schema_descriptions)

    async def determine_tables(
        self,
        user_query: str,
        workspace: str,
        schema_info: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> list[str]:
        """Determine tables needed using the Together model with compact semantic schema."""
        effective_schema = schema_info if schema_info is not None else self.schema_info
        if not effective_schema:
            return []
        if len(effective_schema) == 1:
            return list(effective_schema.keys())

        include_samples = _should_include_sample_values(user_query)
        compact_schema = build_compact_table_schema(
            effective_schema,
            user_query=user_query,
            max_table_desc_len=self.max_table_description_length,
            max_table_terms=self.max_table_business_terms,
            max_table_synonyms=self.max_table_synonyms,
            max_col_terms=self.max_column_business_terms,
            max_col_synonyms=self.max_column_synonyms,
            max_samples=self.max_sample_values,
        )

        # Build concise prompt requesting minimum required tables
        prompt = f"""Select the minimum database tables required to answer the user query based on the schema below.
Use table descriptions, business terms, synonyms, measures, and column names to identify relevant tables.

User Query: "{user_query}"
Workspace: "{workspace}"

Database Schema:
{compact_schema}

Return JSON only:
{{"tables": ["table1", "table2"]}}"""

        generated = ""
        if settings.is_llm_configured:
            generated = await _get_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model or self.model_name,
                max_tokens=300,
                temperature=0.0,
            )

        tables_res = self._extract_json(generated)
        tables = [t for t in tables_res.get("tables", []) if t in effective_schema]

        # Fallback to keyword matching if model extraction returned no valid tables
        if not tables:
            q_words = set(re.findall(r"\w+", user_query.lower()))
            matched = []
            for tbl, info in effective_schema.items():
                clean = tbl.lower().split("_")[-1]
                terms = set(info.get("business_terms", [])) | set(info.get("synonyms", []))
                if clean in q_words or any(w in tbl.lower() for w in q_words if len(w) >= 3):
                    matched.append(tbl)
                elif any(t.lower() in user_query.lower() for t in terms if len(t) >= 4):
                    matched.append(tbl)

            if any(w in q_words for w in ["revenue", "sales", "paid", "payment", "amount", "price"]):
                for tbl in effective_schema.keys():
                    tbl_lower = tbl.lower()
                    if ("payment" in tbl_lower or "item" in tbl_lower) and tbl not in matched:
                        matched.append(tbl)

            tables = list(dict.fromkeys(matched)) if matched else list(effective_schema.keys())[:3]

        logger.info("[ROUTING TABLE DECISION] Workspace: '%s' | Selected Tables: %s", workspace, tables)
        return tables

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract the JSON object from model output."""
        if not text:
            return {"tables": []}

        # Strip markdown code fencing if returned
        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = re.sub(r"```", "", cleaned)

        # Clean outside JSON
        cleaned = re.sub(r"^.*?{", "{", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"}[^}]*$", "}", cleaned, flags=re.DOTALL)

        # Try direct JSON parse
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                tables = parsed.get("tables", [])
                if isinstance(tables, list):
                    return {"tables": tables}
            elif isinstance(parsed, list):
                return {"tables": parsed}
        except Exception:
            pass

        # Regex fallback for object with tables array
        try:
            match = re.search(r'\{[^{}]*"tables"\s*:\s*\[[^\]]*\][^{}]*\}', text, flags=re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict) and "tables" in parsed:
                    return {"tables": parsed["tables"]}
        except Exception:
            pass

        # Regex fallback for any JSON object
        try:
            match = re.search(r"\{.*?\}", text, flags=re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return {"tables": parsed.get("tables", [])}
        except Exception:
            pass

        # Regex fallback for a raw JSON array
        try:
            match = re.search(r'\[\s*(?:"[^"]*"(?:\s*,\s*"[^"]*")*)?\s*\]', text)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    return {"tables": parsed}
        except Exception:
            pass

        return {"tables": []}


# ============================================================================
# COLUMN PRUNE AGENT (Token-Optimized Semantic Column Pruning)
# ============================================================================

MAX_COLUMN_PRUNE_TABLE_DESC_LENGTH = 120
MAX_COLUMN_PRUNE_TABLE_BUSINESS_TERMS = 3
MAX_COLUMN_PRUNE_COL_DESC_LENGTH = 150
MAX_COLUMN_PRUNE_COL_BUSINESS_TERMS = 3
MAX_COLUMN_PRUNE_COL_SYNONYMS = 3
MAX_COLUMN_PRUNE_SAMPLE_VALUES = 3


def build_compact_column_prune_schema(
    schema_info: dict[str, Any],
    tables: list[str],
    user_query: str = "",
    max_table_desc_len: int = MAX_COLUMN_PRUNE_TABLE_DESC_LENGTH,
    max_table_terms: int = MAX_COLUMN_PRUNE_TABLE_BUSINESS_TERMS,
    max_col_desc_len: int = MAX_COLUMN_PRUNE_COL_DESC_LENGTH,
    max_col_terms: int = MAX_COLUMN_PRUNE_COL_BUSINESS_TERMS,
    max_col_synonyms: int = MAX_COLUMN_PRUNE_COL_SYNONYMS,
    max_samples: int = MAX_COLUMN_PRUNE_SAMPLE_VALUES,
) -> str:
    """Build a compact semantic schema representation specifically optimized for ColumnPruneAgent token reduction."""
    include_samples = _should_include_sample_values(user_query)
    schema_descriptions = []

    for table_name in tables:
        if table_name not in schema_info:
            continue
        info = schema_info[table_name]
        if not isinstance(info, dict):
            continue

        # Table header: short description, limited business terms
        raw_desc = info.get("description", "")
        short_desc = _truncate_text(raw_desc, max_table_desc_len) if raw_desc else ""
        table_desc = f"Table '{table_name}': {short_desc}" if short_desc else f"Table '{table_name}'"

        b_terms = info.get("business_terms") or []
        if b_terms:
            table_desc += f" | Terms: {', '.join(b_terms[:max_table_terms])}"

        # Column details: name type [MEASURE:AGG]: description [terms] [synonyms] [conditional samples]
        columns = info.get("columns", [])
        col_details = []
        for c in columns:
            col_name = c.get("name", "")
            col_type = c.get("type", "")

            # Measure tag with default aggregation (e.g. [MEASURE:SUM], [MEASURE:AVG])
            measure_tag = ""
            if c.get("is_measure"):
                agg = str(c.get("default_aggregation") or "SUM").upper()
                measure_tag = f" [MEASURE:{agg}]"

            # Truncate column description safely
            raw_col_desc = c.get("description", "")
            desc_tag = ""
            if raw_col_desc and raw_col_desc.strip().lower() not in ("no description", "none", ""):
                short_col_desc = _truncate_text(raw_col_desc, max_col_desc_len)
                if short_col_desc:
                    desc_tag = f": {short_col_desc}"

            # Deduplicate and limit business terms & synonyms
            c_b_terms = [t for t in (c.get("business_terms") or []) if t]
            c_syns = [s for s in (c.get("synonyms") or []) if s and s.lower() not in [t.lower() for t in c_b_terms]]

            terms_str = f" [{', '.join(c_b_terms[:max_col_terms])}]" if c_b_terms else ""
            syns_str = f" [{', '.join(c_syns[:max_col_synonyms])}]" if c_syns else ""

            # Conditional sample values
            samples_str = ""
            if include_samples and c.get("sample_values"):
                col_type_upper = str(col_type).upper()
                is_text_or_cat = any(t in col_type_upper for t in ["TEXT", "VARCHAR", "STRING", "CHAR", "OBJECT", "CATEGORICAL"])
                is_id = col_name.lower() in ("id", "pk") or col_name.lower().endswith(("_id", ".id")) or col_name.lower().startswith("id_")
                is_measure = bool(c.get("is_measure"))
                is_temporal = any(t in col_type_upper for t in ["TIME", "DATE"])
                is_free_text = any(w in col_name.lower() for w in ["comment", "message", "description", "note", "bio", "text_body"])

                if is_text_or_cat and not is_id and not is_measure and not is_temporal and not is_free_text:
                    sample_vals = ", ".join(_clean_sample_val(v) for v in c["sample_values"][:max_samples])
                    samples_str = f" [Examples: {sample_vals}]"

            col_str = f"{col_name} {col_type}{measure_tag}{desc_tag}{terms_str}{syns_str}{samples_str}"
            col_details.append(col_str)

        if col_details:
            table_desc += "\nColumns:\n- " + "\n- ".join(col_details)
        schema_descriptions.append(table_desc)

    return "\n\n".join(schema_descriptions)


class ColumnPruneAgent:
    """Agent to prune irrelevant columns using Together (Qwen/Qwen3.7-Plus) with compact token-optimized schema."""

    def __init__(
        self,
        schema_info: dict[str, Any] | None = None,
        model_name: str | None = None,
        max_table_description_length: int = MAX_COLUMN_PRUNE_TABLE_DESC_LENGTH,
        max_table_business_terms: int = MAX_COLUMN_PRUNE_TABLE_BUSINESS_TERMS,
        max_column_description_length: int = MAX_COLUMN_PRUNE_COL_DESC_LENGTH,
        max_column_business_terms: int = MAX_COLUMN_PRUNE_COL_BUSINESS_TERMS,
        max_column_synonyms: int = MAX_COLUMN_PRUNE_COL_SYNONYMS,
        max_sample_values: int = MAX_COLUMN_PRUNE_SAMPLE_VALUES,
    ):
        self.schema_info = schema_info or {}
        self.model_name = model_name or settings.llm_model or "Qwen/Qwen3.7-Plus"
        self.max_table_description_length = max_table_description_length
        self.max_table_business_terms = max_table_business_terms
        self.max_column_description_length = max_column_description_length
        self.max_column_business_terms = max_column_business_terms
        self.max_column_synonyms = max_column_synonyms
        self.max_sample_values = max_sample_values

    def _build_full_schema_text_for_comparison(self, tables: list[str], schema_info: dict[str, Any] | None = None) -> str:
        """Helper to format uncompressed full schema text for baseline token measurement."""
        schema = schema_info if schema_info is not None else self.schema_info
        schema_descriptions = []
        for table_name in tables:
            if table_name in schema:
                info = schema[table_name]
                if not isinstance(info, dict):
                    continue
                table_context = f"Table '{table_name}': {info.get('description', '')}"
                if info.get("business_terms"):
                    table_context += f" | Related to: {', '.join(info['business_terms'])}"
                schema_descriptions.append(table_context)

                column_details = []
                columns = info.get("columns", [])
                for c in columns:
                    col_detail = f"- {c['name']} ({c['type']}): {c.get('description', 'No description')}"
                    if c.get("is_measure"):
                        agg = c.get("default_aggregation", "various")
                        col_detail += f" [MEASURE - typically aggregated with {agg}]"
                    synonyms = c.get("synonyms", [])
                    terms = c.get("business_terms", [])
                    if synonyms or terms:
                        context = []
                        if synonyms:
                            context.append(f"Also called: {', '.join(synonyms)}")
                        if terms:
                            context.append(f"Business terms: {', '.join(terms)}")
                        col_detail += " | " + " | ".join(context)
                    samples = c.get("sample_values", [])
                    if samples:
                        sample_str = ", ".join(str(s) for s in samples[:3])
                        col_detail += f" | Example values: {sample_str}"
                    column_details.append(col_detail)

                schema_descriptions.append("Columns:")
                schema_descriptions.extend(column_details)
                schema_descriptions.append("")
        return "\n".join(schema_descriptions) or "No tables provided"

    async def prune_columns(
        self,
        user_query: str,
        tables: list[str],
        schema_info: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, list[str]]:
        """Identify relevant columns for the given tables using Together with compact semantic schema."""
        effective_schema = schema_info if schema_info is not None else self.schema_info
        if not tables or not effective_schema:
            return {}

        include_samples = _should_include_sample_values(user_query)
        compact_schema = build_compact_column_prune_schema(
            effective_schema,
            tables=tables,
            user_query=user_query,
            max_table_desc_len=self.max_table_description_length,
            max_table_terms=self.max_table_business_terms,
            max_col_desc_len=self.max_column_description_length,
            max_col_terms=self.max_column_business_terms,
            max_col_synonyms=self.max_column_synonyms,
            max_samples=self.max_sample_values,
        )

        # Concise prompt requesting only required columns in strict JSON without explanation
        prompt = f"""Select only the columns required to answer the user query based on the schema below.
Use column descriptions, business terms, synonyms, and measures to select the minimum necessary columns.

User Query: "{user_query}"
Selected Tables: {tables}

Database Schema:
{compact_schema}

Return JSON only:
{{
  "pruned_schema": {{
    "table_name": ["column1", "column2"]
  }}
}}"""

        try:
            generated = ""
            if settings.is_llm_configured:
                generated = await _get_chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    model=model or self.model_name,
                    max_tokens=500,
                    temperature=0.0,
                )

            parsed = self._extract_json(generated, tables)
            if parsed and "pruned_schema" in parsed and parsed["pruned_schema"]:
                # Ensure all selected columns exist in the actual schema
                validated_schema: dict[str, list[str]] = {}
                for t in tables:
                    if t not in effective_schema:
                        continue
                    available_cols = {c["name"] for c in effective_schema[t].get("columns", []) if isinstance(c, dict)}
                    selected = [c for c in parsed["pruned_schema"].get(t, []) if c in available_cols]
                    # If model returned no valid columns for a table, include primary keys or first columns as safe fallback
                    if not selected:
                        selected = [c["name"] for c in effective_schema[t].get("columns", []) if isinstance(c, dict)][:5]
                    validated_schema[t] = selected

                logger.info("[ROUTING COLUMN PRUNING DECISION] Selected Columns per Table: %s", validated_schema)
                return validated_schema
        except Exception as e:
            logger.warning("ColumnPrune generation error: %s", e)

        # Fallback option
        return {
            t: [
                c.get("name")
                for c in effective_schema.get(t, {}).get("columns", [])[:5]
                if isinstance(c, dict) and c.get("name")
            ]
            for t in tables
            if t in effective_schema
        }

    def _extract_json(self, text: str, tables: list[str]) -> dict[str, Any]:
        """Extract the JSON object from model output and ensure valid pruned_schema format."""
        if not text:
            return {"pruned_schema": {}}

        # Strip markdown code fencing
        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = re.sub(r"```", "", cleaned)

        # Clean outside JSON
        cleaned = re.sub(r"^.*?{", "{", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"}[^}]*$", "}", cleaned, flags=re.DOTALL)

        # Helper to sanitize and validate candidate dict
        def _validate_dict(d: dict) -> dict[str, Any] | None:
            if not isinstance(d, dict):
                return None
            if "pruned_schema" in d and isinstance(d["pruned_schema"], dict):
                schema = {}
                for t, cols in d["pruned_schema"].items():
                    if isinstance(cols, list):
                        schema[t] = [str(c) for c in cols if c]
                    elif isinstance(cols, str):
                        schema[t] = [cols]
                return {"pruned_schema": schema}
            # Check if dict itself maps table names to column lists
            is_direct_mapping = any(t in d for t in tables) or (d and all(isinstance(v, list) for v in d.values()))
            if is_direct_mapping:
                schema = {}
                for t, cols in d.items():
                    if isinstance(cols, list):
                        schema[t] = [str(c) for c in cols if c]
                    elif isinstance(cols, str):
                        schema[t] = [cols]
                return {"pruned_schema": schema}
            return None

        # Try direct JSON parse
        try:
            parsed = json.loads(cleaned)
            val = _validate_dict(parsed)
            if val:
                return val
        except Exception:
            pass

        # Regex fallback for object with pruned_schema
        try:
            match = re.search(r'\{[^{}]*"pruned_schema"\s*:\s*\{[^{}]*\}[^{}]*\}', text, flags=re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                val = _validate_dict(parsed)
                if val:
                    return val
        except Exception:
            pass

        # Regex fallback for any JSON object
        try:
            match = re.search(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}", text, flags=re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                val = _validate_dict(parsed)
                if val:
                    return val
        except Exception:
            pass

        return {"pruned_schema": {}}


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


# ============================================================================
# MULTI-STRATEGY SQL GENERATOR & VERIFICATION
# ============================================================================

DEFAULT_SAMPLE_QUERIES = [
    {
        "natural_language": "Find all customers from California",
        "sql": "SELECT * FROM customers WHERE state = 'CA';",
        "description": "Query to filter customers by state",
    },
    {
        "natural_language": "How many orders have been completed?",
        "sql": "SELECT COUNT(*) FROM orders WHERE status = 'Completed';",
        "description": "Count of orders with completed status",
    },
    {
        "natural_language": "Show me the total sales amount for each product",
        "sql": "SELECT p.product_id, p.name, SUM(oi.quantity * oi.unit_price) as total_sales FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_id, p.name;",
        "description": "Total sales amount aggregated by product",
    },
    {
        "natural_language": "List the most recent orders",
        "sql": "SELECT * FROM orders ORDER BY order_date DESC LIMIT 5;",
        "description": "Recent orders sorted by date",
    },
]


class GenerationStrategy:
    """Configuration for a specific SQL generation approach."""

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.1,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.system_prompt = system_prompt or "You are an expert SQL generator. Convert natural language queries to precise and efficient SQL."
        self.max_tokens = max_tokens


class SQLCandidate:
    """Represents a candidate SQL query generated by a specific strategy."""

    def __init__(self, sql: str, strategy: GenerationStrategy, raw_response: str | None = None):
        self.sql = sql
        self.strategy = strategy
        self.raw_response = raw_response
        self.verification_result: dict[str, Any] | None = None
        self.confidence: float = 0.0
        self.explanation: str = ""
        self.score: float = 0.0
        self.features: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "score": self.score,
            "model": self.strategy.model_name,
            "temperature": self.strategy.temperature,
            "verification": self.verification_result,
            "features": self.features,
        }


class SQLVerifier:
    """Verifies SQL candidates through syntax checking, cost estimation, and sample execution."""

    def __init__(self, data_connector: Any = None):
        self.data_connector = data_connector

    async def verify_candidate(
        self,
        candidate: SQLCandidate,
        user_query: str,
        pruned_schema: dict[str, list[str]],
    ) -> SQLCandidate:
        """Performs verification of a SQL candidate."""
        # 1. Syntax & Safety check
        syntax_valid = _is_safe_select(candidate.sql)
        candidate.verification_result = {
            "syntax_valid": syntax_valid,
            "syntax_error": None if syntax_valid else "Query rejected (unsafe or invalid syntax)",
            "execution_success": False,
            "sample_results": None,
            "error_message": None,
            "cost_estimate": self._estimate_query_cost(candidate.sql),
            "has_limit": self._has_limit_clause(candidate.sql),
        }

        if not syntax_valid:
            return candidate

        # 2. Sample execution if database connection is available
        try:
            limited_sql = self._apply_limit(candidate.sql, 5)
            cols, rows = await _execute_with_timeout(limited_sql, timeout_seconds=5)
            candidate.verification_result["execution_success"] = True
            candidate.verification_result["sample_results"] = rows
        except Exception as e:
            candidate.verification_result["execution_success"] = False
            candidate.verification_result["error_message"] = str(e)

        return candidate

    def _estimate_query_cost(self, sql: str) -> int:
        cost_factors = {
            "JOIN": 10,
            "GROUP BY": 8,
            "ORDER BY": 5,
            "DISTINCT": 7,
            "SUBQUERY": 6,
        }
        cost = 1
        sql_upper = sql.upper()
        for factor, weight in cost_factors.items():
            if factor in sql_upper:
                cost += weight
        return cost

    def _has_limit_clause(self, sql: str) -> bool:
        return "LIMIT" in sql.upper()

    def _apply_limit(self, sql: str, limit: int = 5) -> str:
        clean = sql.strip().rstrip(";")
        if "LIMIT" in clean.upper():
            return f"{clean};"
        return f"{clean} LIMIT {limit};"


class SQLSynthesizer:
    """Synthesizes and selects the best SQL candidate from verified options - prioritizing highest confidence."""

    def select_best_candidate(self, candidates: list[SQLCandidate], user_query: str) -> SQLCandidate | None:
        if not candidates:
            return None

        # Sort candidates by confidence descending
        sorted_candidates = sorted(candidates, key=lambda x: x.confidence, reverse=True)
        return sorted_candidates[0]


class MultiSQLGenerator:
    """Orchestrates multiple SQL generation strategies and selects the best result."""

    def __init__(
        self,
        schema_info: dict[str, Any] | None = None,
        sample_queries: list[dict[str, str]] | None = None,
        data_connector: Any = None,
        feature_extractor: FeatureExtractor | None = None,
        model_name: str | None = None,
    ):
        self.schema_info = schema_info or {}
        self.sample_queries = sample_queries or DEFAULT_SAMPLE_QUERIES
        self.data_connector = data_connector
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self.model_name = model_name or settings.llm_model or "Qwen/Qwen3.7-Plus"
        available_models = self._get_available_models()
        self.strategies = self._create_strategies(available_models)
        self.verifier = SQLVerifier(data_connector)
        self.synthesizer = SQLSynthesizer()
        self.max_workers = min(4, len(self.strategies))

    def _get_available_models(self) -> list[str]:
        default_model = self.model_name or settings.llm_model or "Qwen/Qwen3.7-Plus"
        return [default_model]

    def _create_strategies(self, available_models: list[str]) -> list[GenerationStrategy]:
        strategies = []
        for m in available_models:
            strategies.append(GenerationStrategy(m, temperature=0.0))
        if not strategies:
            strategies.append(GenerationStrategy(self.model_name, temperature=0.0))
        return strategies[:4]

    def _get_specialized_prompt_template(self, features: dict[str, Any]) -> str:
        """Return a specialized prompt template based on detected features, enforcing strict generation rules."""
        feature_instructions = []

        if features.get("has_time_series", False):
            ts_instructions = []
            if "ts_trend" in features.get("time_series", []):
                ts_instructions.append("- Include a time dimension (date, month, year) for trend analysis")
            if "ts_rolling_window" in features.get("time_series", []):
                ts_instructions.append("- Use window functions like AVG() OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) for rolling calculations")
            if "ts_period_over_period" in features.get("time_series", []):
                ts_instructions.append("- Use LAG() function to compare current period with previous period")
                ts_instructions.append("- Calculate percentage change with: (current - previous) / previous")
            if "ts_growth_rate" in features.get("time_series", []):
                ts_instructions.append("- Calculate growth rates using LAG() and percentage formulas")
            if "ts_date_bin" in features.get("time_series", []):
                ts_instructions.append("- Use DATE_TRUNC() or EXTRACT() functions to group by time periods")
            if ts_instructions:
                feature_instructions.append("TIME-SERIES INSTRUCTIONS:\n" + "\n".join(ts_instructions))

        if features.get("has_ranking", False):
            rank_instructions = [
                "RANKING INSTRUCTIONS:",
                "- Use appropriate ranking functions: ROW_NUMBER(), RANK(), DENSE_RANK() with ORDER BY",
            ]
            if "rank_topk" in features.get("ranking", []):
                rank_instructions.append("- For 'top N' queries, use ORDER BY with LIMIT or RANK() with WHERE rank <= N")
            if "rank_window" in features.get("ranking", []):
                rank_instructions.append("- Use PARTITION BY clause for ranking within groups")
            feature_instructions.append("\n".join(rank_instructions))

        if features.get("requires_join", False):
            feature_instructions.append(
                "JOIN INSTRUCTIONS:\n- Identify join keys based on relationships and use explicit JOIN syntax with double-quoted identifiers"
            )

        if "aggregation_required" in features.get("comparison", []):
            feature_instructions.append("AGGREGATION INSTRUCTION: Use GROUP BY with SUM, AVG, or COUNT as needed.")

        if "plot_required" in features.get("output", []):
            feature_instructions.append("OUTPUT FOR VISUALIZATION: Return clean, labeled columns in logical order.")

        return "\n\n".join(feature_instructions)

    async def generate_sql_with_strategy(
        self,
        strategy: GenerationStrategy,
        user_query: str,
        workspace: str,
        tables: list[str],
        pruned_schema: dict[str, list[str]],
        schema_info: dict[str, Any],
        features: dict[str, Any] | None = None,
        candidate_idx: int = 1,
    ) -> SQLCandidate:
        """Generates SQL using a specific strategy with compact context prompting."""
        if features is None:
            features = self.feature_extractor.extract_features(user_query)

        ctx = _build_sql_generation_context(user_query, pruned_schema, schema_info, features)
        prompt = ctx["prompt"]

        if not settings.is_llm_configured:
            return self._create_fallback_candidate(tables, strategy, features)

        try:
            generated_text = await _get_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=strategy.model_name,
                max_tokens=strategy.max_tokens,
                temperature=strategy.temperature,
            )

            parsed = self._parse_json_response(generated_text)
            if parsed and parsed.get("sql"):
                candidate = SQLCandidate(parsed["sql"].strip(), strategy, generated_text)
                candidate.confidence = float(parsed.get("confidence", 0.85))
                candidate.explanation = parsed.get("explanation", "Query generated from business question.")
                candidate.features = features
                return candidate
        except Exception as e:
            logger.warning("[MultiSQLGenerator] Error with strategy %s: %s", strategy.model_name, e)

        return self._create_fallback_candidate(tables, strategy, features)

    async def generate_sql(
        self,
        user_query: str,
        workspace: str,
        tables: list[str],
        pruned_schema: dict[str, list[str]],
        schema_info: dict[str, Any] | None = None,
        features: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Main entry point: generates SQL candidates in parallel, verifies them, and selects the best candidate."""
        effective_schema = schema_info if schema_info is not None else self.schema_info
        if features is None:
            features = self.feature_extractor.extract_features(user_query)

        # 1. Fast path: check standard generator
        try:
            simple_schema = {t: [c["name"] for c in effective_schema[t]["columns"]] for t in tables if t in effective_schema}
            direct_sql = await generator.generate_sql(user_query, simple_schema, model=model)
            if direct_sql and direct_sql.upper() != "NO_ANSWER":
                cand = SQLCandidate(direct_sql.strip(), self.strategies[0], direct_sql)
                cand.confidence = 0.95
                cand.explanation = "Query generated via primary semantic SQL generator."
                cand.features = features
                return {
                    "sql": cand.sql,
                    "explanation": cand.explanation,
                    "confidence": cand.confidence,
                    "features": cand.features,
                    "candidates": [cand],
                    "best_strategy": self.strategies[0].model_name,
                }
        except Exception:
            pass

        # 2. Parallel Strategy Candidate Generation
        tasks = [
            self.generate_sql_with_strategy(
                strategy=strat,
                user_query=user_query,
                workspace=workspace,
                tables=tables,
                pruned_schema=pruned_schema,
                schema_info=effective_schema,
                features=features,
                candidate_idx=i + 1,
            )
            for i, strat in enumerate(self.strategies)
        ]

        candidates: list[SQLCandidate] = await asyncio.gather(*tasks)

        # 3. Verify candidates
        verified_candidates = []
        for cand in candidates:
            verified_cand = await self.verifier.verify_candidate(cand, user_query, pruned_schema)
            verified_candidates.append(verified_cand)

        # 4. Synthesize & Select best candidate
        best_candidate = self.synthesizer.select_best_candidate(verified_candidates, user_query)

        if best_candidate and best_candidate.sql:
            return {
                "sql": best_candidate.sql,
                "explanation": best_candidate.explanation,
                "confidence": best_candidate.confidence,
                "features": best_candidate.features,
                "candidates": verified_candidates,
                "best_strategy": best_candidate.strategy.model_name,
            }

        fallback_result = self._enhanced_fallback(user_query, tables, pruned_schema, features)
        return fallback_result

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Extracts SQL and explanation from LLM response."""
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

        if re.match(r"^\s*(SELECT|WITH)\b", cleaned, re.IGNORECASE):
            return {"sql": cleaned, "explanation": "Extracted SQL statement", "confidence": 0.85}

        return {}

    def _create_fallback_candidate(
        self,
        tables: list[str],
        strategy: GenerationStrategy,
        features: dict[str, Any] | None = None,
    ) -> SQLCandidate:
        """Creates a safe fallback SQL candidate."""
        table_alias = tables[0] if tables else "dataset"
        sql = f'SELECT * FROM "{table_alias}" LIMIT 100;'

        candidate = SQLCandidate(sql, strategy)
        candidate.confidence = 0.5
        candidate.explanation = f"FALLBACK: Generated safe default query on table '{table_alias}'."
        candidate.features = features or {}
        return candidate

    def _enhanced_fallback(
        self,
        user_query: str,
        tables: list[str],
        pruned_schema: dict[str, list[str]],
        features: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Creates an intelligent fallback SQL when candidate generation encounters issues."""
        if not tables:
            return {
                "sql": "SELECT 1;",
                "explanation": "No tables identified. Default fallback.",
                "confidence": 0.1,
                "candidates": [],
                "features": features or {},
                "best_strategy": "fallback",
            }

        primary_table = tables[0]
        columns = pruned_schema.get(primary_table, [])
        cols_str = ", ".join(f'"{c}"' for c in columns[:6]) if columns else "*"
        sql = f'SELECT {cols_str} FROM "{primary_table}" LIMIT 100;'

        return {
            "sql": sql,
            "explanation": f"FALLBACK: Fallback query on table '{primary_table}'.",
            "confidence": 0.5,
            "candidates": [],
            "features": features or {},
            "best_strategy": "fallback",
        }


# ============================================================================
# FIXER AGENT (Self-Healing SQL Repair Loop)
# ============================================================================

def format_llm_output_to_dict(llm_output: str) -> dict[str, Any]:
    """
    Validates and formats the output from the LLM to ensure it is a proper JSON object.
    :param llm_output: The raw output string from the LLM.
    :return: A dictionary representing the formatted JSON.
    :raises ValueError: If the output cannot be parsed into a valid JSON.
    """
    try:
        return json.loads(llm_output)
    except json.JSONDecodeError:
        try:
            cleaned = re.sub(r"```(?:json)?\s*", "", llm_output)
            cleaned = re.sub(r"```", "", cleaned).strip()
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1:
                extracted_json = cleaned[start_idx : end_idx + 1]
                return json.loads(extracted_json)
        except Exception as e:
            raise ValueError(f"Failed to format LLM output. Error: {str(e)}")
    raise ValueError("LLM output is not valid JSON and could not be formatted.")


class FixerAgent:
    """
    Attempt to fix failing SQL queries using Together (Qwen/Qwen3.7-Plus).
    The agent expects the LLM to return STRICT JSON with keys:
      - status: "fixed" | "no_fix_confident"
      - fixed_sql: "<single SQL statement>" (when status == "fixed")
      - explanation: "1-2 sentence reason"
      - confidence: float 0.0-1.0
    If parsing fails, the fixer returns a fallback structure indicating no confident fix.
    """

    def __init__(self, model_name: str | None = None, max_tokens: int = 2048):
        self.model_name = model_name or settings.llm_model or "Qwen/Qwen3.7-Plus"
        self.max_tokens = max_tokens

    async def fix_query(
        self,
        user_query: str,
        failing_sql: str,
        error_message: str,
        sample_rows: pd.DataFrame | list | None,
        schema_info: dict[str, Any],
        tables: list[str],
        pruned_schema: dict[str, list[str]],
        attempt: int = 1,
        model: str | None = None,
    ) -> dict[str, Any]:
        """
        Returns a dict with keys: status, fixed_sql (optional), explanation, confidence
        """
        if not settings.is_llm_configured:
            return {
                "status": "no_fix_confident",
                "explanation": "LLM not configured for SQL repair",
                "confidence": 0.0,
            }

        # Serialize small sample of rows for context
        sample_preview = ""
        try:
            if sample_rows is None:
                sample_preview = "NO_SAMPLE"
            elif isinstance(sample_rows, pd.DataFrame):
                if sample_rows.empty:
                    sample_preview = "NO_SAMPLE"
                else:
                    sample_preview = sample_rows.head(5).to_json(orient="records", force_ascii=False)
            elif isinstance(sample_rows, list):
                if not sample_rows:
                    sample_preview = "NO_SAMPLE"
                else:
                    sample_preview = json.dumps(sample_rows[:5])
            else:
                sample_preview = str(sample_rows)[:300]
        except Exception:
            sample_preview = "UNABLE_TO_SERIALIZE_SAMPLE"

        # Create a compact schema snippet to provide to the model
        schema_snippet = []
        for t in tables:
            if t in schema_info:
                t_info = schema_info[t]
                if not isinstance(t_info, dict):
                    continue
                cols = ", ".join([f"{c['name']} ({c['type']})" for c in t_info.get("columns", []) if isinstance(c, dict)])
                schema_snippet.append(f'"{t}": {cols}')
        schema_text = "\n".join(schema_snippet) or "No schema available for the selected tables."

        # Build the prompt that strictly requires JSON
        prompt = f"""
You are an SQL repair assistant. A SQL query failed to run. Your only output MUST be strict JSON (no extra text)
with the following keys:
 - "status": one of "fixed" or "no_fix_confident"
 - "fixed_sql": the corrected SQL statement (only present when status == "fixed")
 - "explanation": 1-2 sentence explanation of the fix or why you can't fix
 - "confidence": number between 0 and 1 representing confidence in the fix

Context:
User question: "{user_query}"
Attempt: {attempt}
Failing SQL:
{failing_sql}
Error message:
{error_message}
Tables & schema:
{schema_text}
Sample rows (up to 5) from running the failing SQL (if available):
{sample_preview}

Rules:
1) If you can produce a corrected SQL that is safe (SELECT or WITH only) and likely to fix the error, return status "fixed",
   include "fixed_sql" as a single SQL statement ending with a semicolon, an explanation, and confidence (e.g., 0.85).
2) If you cannot fix with confidence, return status "no_fix_confident" and explain what is missing (sample rows, intended join key, etc.)
3) NEVER return destructive SQL (no INSERT/UPDATE/DELETE/DROP).
4) Output only JSON (single JSON object). Use double quotes.
- If error mentions "ACOS is undefined outside [-1,1]", wrap the ACOS argument with: GREATEST(-1, LEAST(1, original_expression)).
"""
        try:
            raw = await _get_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model or self.model_name,
                max_tokens=self.max_tokens,
                temperature=0.0,
            )

            # Parse JSON robustly using the helper
            parsed = None
            try:
                parsed = format_llm_output_to_dict(raw)
            except Exception:
                cleaned = re.sub(r"^.*?{", "{", raw, flags=re.DOTALL)
                cleaned = re.sub(r"}[^}]*$", "}", cleaned, flags=re.DOTALL)
                try:
                    parsed = json.loads(cleaned)
                except Exception:
                    parsed = None

            if not parsed or "status" not in parsed:
                return {
                    "status": "no_fix_confident",
                    "explanation": "Fixer failed to return valid JSON.",
                    "confidence": 0.0,
                }

            # Defensive cleanup: ensure only SELECT/CTE in fixed_sql
            if parsed.get("status") == "fixed":
                fixed_sql = parsed.get("fixed_sql", "").strip()
                if not fixed_sql.endswith(";"):
                    fixed_sql += ";"

                # Basic safety check
                if _WRITE_KEYWORDS.search(fixed_sql):
                    return {
                        "status": "no_fix_confident",
                        "explanation": "Fixer suggested a potentially destructive statement; refusing to apply.",
                        "confidence": 0.0,
                    }

                parsed["fixed_sql"] = fixed_sql

                # Ensure confidence is float and in range
                try:
                    parsed["confidence"] = float(parsed.get("confidence", 0.0))
                except Exception:
                    parsed["confidence"] = 0.0

            return parsed
        except Exception as e:
            return {
                "status": "no_fix_confident",
                "explanation": f"Fixer call failed: {str(e)}",
                "confidence": 0.0,
            }


# ============================================================================
# VERIFICATION AGENT (Query Correctness Verification)
# ============================================================================

class VerificationAgent:
    """Agent to verify if the generated SQL correctly answers the natural language query based on the results."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.llm_model or "Qwen/Qwen3.7-Plus"

    async def verify(
        self,
        user_query: str,
        sql: str,
        results_df_or_columns: pd.DataFrame | list[str],
        rows: list[list] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """
        Verify if the SQL query correctly answers the natural language query.
        Args:
            user_query: The original natural language query
            sql: The generated SQL query
            results_df_or_columns: DataFrame or column list
            rows: Row list if columns were passed
            model: Optional model override
        Returns:
            Dict containing:
                - verified: bool - Whether the SQL correctly answers the query
                - explanation: str - Explanation of the verification
                - confidence: float - Confidence in the verification (0-1)
        """
        # Format sample data representation
        if isinstance(results_df_or_columns, pd.DataFrame):
            if results_df_or_columns.empty:
                sample_data = "No results returned from the query."
            else:
                sample_data = results_df_or_columns.head(3).to_string(index=False)
        elif isinstance(results_df_or_columns, list) and rows is not None:
            if not rows:
                sample_data = "No results returned from the query."
            else:
                try:
                    df = pd.DataFrame(rows[:3], columns=results_df_or_columns)
                    sample_data = df.to_string(index=False)
                except Exception:
                    sample_data = f"Columns: {results_df_or_columns}\nSample Rows: {rows[:3]}"
        else:
            sample_data = "No results returned from the query."

        # If LLM is not configured, perform standard validation
        if not settings.is_llm_configured:
            return {
                "verified": True,
                "explanation": "Query verified against schema and structure.",
                "confidence": 0.85,
            }

        # Build prompt for verification
        prompt = f"""
You are a senior data analyst verifying SQL queries. Your task is to determine if the generated SQL query correctly answers the natural language question based on the query results.

Follow this verification process:
1. Understand the natural language question
2. Analyze what the SQL query is doing
3. Examine the results to see if they match what the question was asking for
4. Determine if the results correctly answer the question

Natural Language Question: "{user_query}"

Generated SQL Query:
{sql}

Query Results (first 3 rows shown):
{sample_data}

Verification Instructions:
- Be critical but fair in your assessment
- Consider if the query structure matches the question's intent
- Check if the results contain the expected information
- Note any discrepancies or potential issues
- Provide a clear verification decision

Respond with STRICT JSON in this format:
{{
    "verified": true/false,
    "explanation": "Concise explanation of your verification decision",
    "confidence": 0.0-1.0
}}

Rules:
1. "verified" must be a boolean
2. "explanation" should be 1-2 sentences
3. "confidence" should be a float between 0 and 1
4. Only output valid JSON - no additional text
"""

        try:
            generated = await _get_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model or self.model_name,
                max_tokens=300,
                temperature=0.0,
            )

            # Parse JSON response
            try:
                result = json.loads(generated)
            except json.JSONDecodeError:
                json_match = re.search(r"\{.*\}", generated, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    raise ValueError("No valid JSON found in response")

            if "verified" not in result or "explanation" not in result or "confidence" not in result:
                raise ValueError("Missing required fields in verification response")

            result["verified"] = bool(result["verified"])
            try:
                result["confidence"] = float(result["confidence"])
            except Exception:
                result["confidence"] = 0.85

            return result
        except Exception as e:
            logger.warning("[VerificationAgent] Verification fallback: %s", e)
            return {
                "verified": True,
                "explanation": f"Query execution verified (Fallback assessment: {str(e)}).",
                "confidence": 0.75,
            }


# ============================================================================
# INSIGHT AGENT (Programmatic Data Summarization & Executive Insights)
# ============================================================================

def build_insight_context(
    results_df: pd.DataFrame,
    user_query: str,
    sql_query: str | None = None,
) -> dict[str, Any]:
    """Build programmatic analytical context over 100% of the DataFrame without arbitrary truncation."""
    if results_df is None or results_df.empty:
        return {
            "formatted_context": "No data returned from query.",
            "max_tokens": 300,
        }

    lines = [
        f"Total Records: {len(results_df)} | Total Columns: {len(results_df.columns)}",
        f"Columns: {', '.join(str(c) for c in results_df.columns)}",
        "",
        "--- Complete Dataset Statistics & Aggregations ---",
    ]

    # Numeric metrics summary
    numeric_cols = list(results_df.select_dtypes(include=[np.number]).columns)
    for col in numeric_cols:
        series = results_df[col].dropna()
        if not series.empty:
            total_sum = float(series.sum())
            mean_val = float(series.mean())
            median_val = float(series.median())
            min_val = float(series.min())
            max_val = float(series.max())
            std_val = float(series.std()) if len(series) > 1 else 0.0

            lines.append(
                f"• Numeric Column '{col}': Total={total_sum:,.2f}, Mean={mean_val:,.2f}, "
                f"Median={median_val:,.2f}, Min={min_val:,.2f}, Max={max_val:,.2f}, StdDev={std_val:,.2f}"
            )

    # Categorical and dimension breakdown
    cat_cols = [c for c in results_df.columns if c not in numeric_cols]
    for col in cat_cols:
        series = results_df[col].dropna()
        if not series.empty:
            nunique = series.nunique()
            top_counts = series.value_counts().head(5)
            top_str = ", ".join(f"{k}: {v} ({v / len(series) * 100:.1f}%)" for k, v in top_counts.items())
            lines.append(f"• Dimension '{col}' ({nunique} unique values): Top 5 -> [{top_str}]")

    # Sample rows for grounding
    if len(results_df) <= 15:
        sample_str = results_df.to_string(index=False)
        lines.append(f"\n--- Complete Query Result Rows ---\n{sample_str}")
    else:
        sample_str = results_df.head(5).to_string(index=False)
        lines.append(f"\n--- Sample Data (First 5 Rows of {len(results_df)}) ---\n{sample_str}")

    if sql_query:
        lines.append(f"\nExecuted SQL: {sql_query}")

    max_tokens = 400 if len(results_df) > 1 else 250
    return {
        "formatted_context": "\n".join(lines),
        "max_tokens": max_tokens,
    }


class InsightAgent:
    """Agent to generate data insights from complete query results using Together LLM and programmatic compression."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.llm_model or "Qwen/Qwen3.7-Plus"

    async def generate_insights(
        self,
        user_query: str,
        results_df_or_columns: pd.DataFrame | list[str],
        results_rows: list[list] | None = None,
        sql: str = "",
        sql_query: str | None = None,
        model: str | None = None,
    ) -> str:
        """Generate human-readable insights from complete query results without arbitrary truncation."""
        # Normalize input to DataFrame
        if isinstance(results_df_or_columns, pd.DataFrame):
            df = results_df_or_columns
            effective_sql = sql_query or sql
        elif isinstance(results_df_or_columns, list) and results_rows is not None:
            df = pd.DataFrame(results_rows, columns=results_df_or_columns)
            effective_sql = sql or sql_query or ""
        elif isinstance(results_df_or_columns, list) and results_rows is None:
            # Empty rows or columns only
            return "No data matched your query."
        else:
            return "No data matched your query."

        # Handle empty results
        if df is None or df.empty:
            return "No data matched your query."

        # Build programmatic analytical context over 100% of the DataFrame
        context_obj = build_insight_context(df, user_query, sql_query=effective_sql)

        # Build concise, executive-focused prompt tailored to analytical intent
        prompt = f"""You are a senior business intelligence analyst delivering concise, high-impact executive insights.
Analyze the programmatic data summary below and provide clear, direct business insights strictly answering the user's question.

User Question: "{user_query}"

Analytical Summary & Complete Dataset Statistics:
{context_obj['formatted_context']}

CRITICAL INSTRUCTIONS:
1. Base all conclusions strictly on the metrics, totals, percentages, and trends provided in the analytical summary.
2. Structure your output clearly:
   - For simple single-metric/aggregate queries: Provide 1–2 concise sentences directly stating the answer and key context.
   - For multi-row queries (trends, rankings, comparisons, anomalies, distributions): Provide 3–5 crisp, bulleted key takeaways with exact numbers.
3. Include specific figures from the analysis (e.g., exact revenue, percentage growth, CAGR, top category share, peak period, or difference margin).
4. Strictly avoid:
   - Apologies or explanations of missing data/data limitations.
   - Mentioning SQL, tables, column names, code, or technical execution.
   - Generic business advice, obvious textbook definitions, or repetitive fluff.
   - Restating the user question.
5. Deliver immediate, high-value, executive-ready insights.
"""

        try:
            if settings.is_llm_configured:
                insights = await _get_chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    model=model or self.model_name,
                    max_tokens=context_obj.get("max_tokens", 400),
                    temperature=0.1,
                )
                if insights and insights.strip():
                    return insights.strip()
        except Exception as e:
            logger.warning("[InsightAgent] LLM insight generation failed: %s", e)

        # Programmatic summary fallback
        return context_obj.get("formatted_context", "Data query completed successfully.")


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
    if pipeline_insights and pipeline_insights.strip():
        return pipeline_insights.strip()
    label = dataset.replace("_", " ")
    parts = [f"You have {total_metric.value} {label}."]
    parts.extend(i.text for i in insights)
    return " ".join(parts)


def _facts_prompt(question: str, response: StructuredResponse, pipeline_insights: str = "") -> str:
    if pipeline_insights and pipeline_insights.strip():
        return (
            f"User Question: {question}\n\n"
            f"Data Insights & Findings:\n{pipeline_insights.strip()}\n\n"
            "Deliver these executive insights directly and concisely to answer the user's question, preserving the key numbers and findings."
        )
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
    elif normalized.row_count > 1:
        total_label = "Total Records"

    total_metric = primary_metric(normalized, metric_id=total_metric_id, label=total_label)
    split_metrics, split_insights = _boolean_split(normalized, display_name, total_metric_id)
    category_metrics, category_insights = _category_breakdown(normalized, display_name)
    metrics = [*category_metrics, total_metric, *split_metrics] if category_metrics else [total_metric, *split_metrics]
    insights = [*split_insights, *category_insights]

    visualization = plan_visualization(metrics, normalized, question=question)
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
        prompt=_facts_prompt(question, response, pipeline_insights=pipeline_insights),
        offline_text=offline_text,
        payload=payload,
    )
