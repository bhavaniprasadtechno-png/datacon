import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

from app.agents.types import AgentPrep
from app.config import settings
from app.query_engine.executor import answer_question
from app.query_engine.extract import column_index
from app.rag.chroma_store import query as chroma_query

logger = logging.getLogger(__name__)


# ============================================================================
# LLM & YAML HELPERS
# ============================================================================

def get_together_chat_completion(
    model_name: str = "Qwen/Qwen3.7-Plus",
    messages: list = None,
    agent_name: str = "Diagnostic Agent",
    max_tokens: int = 700,
    **kwargs
) -> str:
    """Helper to call Together or LiteLLM chat completions."""
    clean_model_name = (model_name or settings.llm_model or "Qwen/Qwen3.7-Plus").replace("together_ai/", "").replace("openai/", "")
    api_key = settings.together_api_key or os.getenv("TOGETHER_API_KEY")

    if api_key:
        try:
            from together import Together
            client = Together(api_key=api_key)
            try:
                stream = client.chat.completions.create(
                    model=clean_model_name,
                    messages=messages or [],
                    stream=True,
                    max_tokens=max_tokens,
                    **kwargs
                )
                text_chunks = []
                for chunk in stream:
                    if hasattr(chunk, "choices") and chunk.choices:
                        content = getattr(chunk.choices[0].delta, "content", None) or getattr(chunk.choices[0], "text", None) or ""
                        if content:
                            text_chunks.append(content)
                result_text = "".join(text_chunks).strip()
                if result_text:
                    return result_text
            except Exception:
                response = client.chat.completions.create(
                    model=clean_model_name,
                    messages=messages or [],
                    stream=False,
                    max_tokens=max_tokens,
                    **kwargs
                )
                if hasattr(response, "choices") and response.choices:
                    return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Together client exception in {agent_name}: {e}")

    try:
        import litellm
        target_model = clean_model_name if "together" in clean_model_name.lower() else f"together_ai/{clean_model_name}"
        response = litellm.completion(
            model=target_model,
            messages=messages or [],
            max_tokens=max_tokens,
            temperature=kwargs.get("temperature", 0.1),
        )
        if hasattr(response, "choices") and response.choices:
            return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LiteLLM completion error in {agent_name}: {e}")

    return ""


def load_yaml_schema_from_content(yaml_content: str) -> Dict[str, Any]:
    """Convert YAML string to schema_info dict - supports BOTH old and new formats."""
    TYPE_MAPPING = {
        "VARCHAR": "TEXT", "INTEGER": "INTEGER", "FLOAT": "REAL",
        "TIMESTAMP": "TIMESTAMP", "BOOLEAN": "INTEGER", "DATE": "DATE", "OBJECT": "TEXT"
    }

    try:
        schema_data = yaml.safe_load(yaml_content)
        if not schema_data:
            return {}

        schema_info = {}

        # === NEW FORMAT: tables: [...] array ===
        if "tables" in schema_data and isinstance(schema_data["tables"], list):
            tables = schema_data["tables"]
            if isinstance(tables, dict):
                tables = [tables]

            for table in tables:
                if not isinstance(table, dict):
                    continue
                table_name = table.get("table_name")
                if not table_name:
                    continue

                primary_key_columns = set()
                raw_pks = table.get("primary_key", [])
                if isinstance(raw_pks, str):
                    primary_key_columns.add(raw_pks)
                elif isinstance(raw_pks, list):
                    for pk in raw_pks:
                        if isinstance(pk, list):
                            for col in pk:
                                if isinstance(col, str):
                                    primary_key_columns.add(col)
                        elif isinstance(pk, str):
                            primary_key_columns.add(pk)

                column_info = []
                for col in table.get("columns", []):
                    col_type = str(col.get("type", "")).upper()
                    mapped_type = TYPE_MAPPING.get(col_type, col_type)
                    is_pk = col.get("name", "") in primary_key_columns or bool(col.get("primary_key", False))
                    if is_pk and col.get("name"):
                        primary_key_columns.add(col.get("name"))

                    column_info.append({
                        "name": col.get("name", ""),
                        "type": mapped_type,
                        "description": col.get("description", ""),
                        "is_measure": col.get("is_measure", False),
                        "default_aggregation": col.get("default_aggregation"),
                        "synonyms": col.get("synonyms", []),
                        "business_terms": col.get("business_terms", []),
                        "sample_values": col.get("sample_values", []),
                        "formatting": col.get("formatting", {}),
                        "primary_key": is_pk,
                        "foreign_key": col.get("foreign_key")
                    })

                clean_table_name = Path(table_name).stem

                # Extract and normalize foreign keys from YAML
                raw_fks = table.get("foreign_keys", []) or table.get("relationships", [])
                normalized_fks = []
                if isinstance(raw_fks, list):
                    for fk in raw_fks:
                        if isinstance(fk, dict):
                            from_c = fk.get("from_column") or fk.get("column") or fk.get("from")
                            to_t = fk.get("to_table") or fk.get("foreign_table") or fk.get("to")
                            to_c = fk.get("to_column") or fk.get("foreign_column") or fk.get("to_col")
                            if to_t:
                                to_t = Path(to_t).stem
                            if from_c and to_t and to_c:
                                normalized_fks.append({
                                    "from_column": str(from_c),
                                    "to_table": str(to_t),
                                    "to_column": str(to_c),
                                    "confidence": float(fk.get("confidence", 1.0)),
                                    "non_null_fraction": float(fk.get("non_null_fraction", 1.0)),
                                    "cardinality": fk.get("cardinality", "many-to-one")
                                })

                schema_info[clean_table_name] = {
                    "description": table.get("description", f"Table containing {table_name} information"),
                    "synonyms": table.get("synonyms", []),
                    "business_terms": table.get("business_terms", []),
                    "columns": column_info,
                    "primary_key": list(primary_key_columns),
                    "foreign_keys": normalized_fks,
                    "s3_path": (
                        table.get("s3_path")
                        or table.get("source")
                        or table.get("table_path")
                    )
                }

        # === OLD FORMAT: table names as root-level keys ===
        elif "tables" not in schema_data:
            for key, value in schema_data.items():
                if key in ["verified_queries", "relationships"] or not isinstance(value, dict):
                    continue

                table_name = key
                table_info = value

                if "columns" not in table_info:
                    continue

                primary_key_columns = set()
                raw_pks = table_info.get("primary_key", [])
                if isinstance(raw_pks, str):
                    primary_key_columns.add(raw_pks)
                elif isinstance(raw_pks, list):
                    for pk in raw_pks:
                        if isinstance(pk, list):
                            for col in pk:
                                if isinstance(col, str):
                                    primary_key_columns.add(col)
                        elif isinstance(pk, str):
                            primary_key_columns.add(pk)

                column_info = []
                for col in table_info.get("columns", []):
                    col_type = str(col.get("type", "")).upper()
                    mapped_type = TYPE_MAPPING.get(col_type, col_type)
                    is_pk = col.get("primary_key", False) or (col.get("name", "") in primary_key_columns)
                    if is_pk and col.get("name"):
                        primary_key_columns.add(col.get("name"))
                    column_info.append({
                        "name": col.get("name", ""),
                        "type": mapped_type,
                        "description": col.get("description", ""),
                        "is_measure": col.get("is_measure", False),
                        "default_aggregation": col.get("default_aggregation"),
                        "synonyms": col.get("synonyms", []),
                        "business_terms": col.get("business_terms", []),
                        "sample_values": col.get("sample_values", []),
                        "formatting": col.get("formatting", {}),
                        "primary_key": is_pk,
                        "foreign_key": col.get("foreign_key")
                    })

                clean_table_name = Path(table_name).stem
                raw_fks = table_info.get("foreign_keys", []) or table_info.get("relationships", [])
                normalized_fks = []
                if isinstance(raw_fks, list):
                    for fk in raw_fks:
                        if isinstance(fk, dict):
                            from_c = fk.get("from_column") or fk.get("column")
                            to_t = fk.get("to_table") or fk.get("foreign_table")
                            to_c = fk.get("to_column") or fk.get("foreign_column")
                            if to_t:
                                to_t = Path(to_t).stem
                            if from_c and to_t and to_c:
                                normalized_fks.append({
                                    "from_column": str(from_c),
                                    "to_table": str(to_t),
                                    "to_column": str(to_c),
                                    "confidence": float(fk.get("confidence", 1.0)),
                                    "non_null_fraction": float(fk.get("non_null_fraction", 1.0)),
                                    "cardinality": fk.get("cardinality", "many-to-one")
                                })

                schema_info[clean_table_name] = {
                    "description": table_info.get("description", f"Table containing {table_name} information"),
                    "synonyms": table_info.get("synonyms", []),
                    "business_terms": table_info.get("business_terms", []),
                    "columns": column_info,
                    "primary_key": list(primary_key_columns),
                    "foreign_keys": normalized_fks,
                    "s3_path": table_info.get("s3_path") or table_info.get("table_path")
                }

        # Process top-level relationships in YAML if present
        top_relationships = schema_data.get("relationships", [])
        if isinstance(top_relationships, list):
            for rel in top_relationships:
                if isinstance(rel, dict):
                    from_t = Path(rel.get("from_table", "")).stem if rel.get("from_table") else ""
                    to_t = Path(rel.get("to_table", "")).stem if rel.get("to_table") else ""
                    from_c = rel.get("from_column") or rel.get("column")
                    to_c = rel.get("to_column") or rel.get("foreign_column")
                    if from_t in schema_info and to_t and from_c and to_c:
                        schema_info[from_t].setdefault("foreign_keys", []).append({
                            "from_column": str(from_c),
                            "to_table": str(to_t),
                            "to_column": str(to_c),
                            "confidence": float(rel.get("confidence", 1.0)),
                            "non_null_fraction": float(rel.get("non_null_fraction", 1.0)),
                            "cardinality": rel.get("cardinality", "many-to-one")
                        })

        return schema_info

    except Exception as e:
        logger.error(f"Error loading YAML schema: {str(e)}")
        raise RuntimeError(f"Error loading YAML: {str(e)}")


# ============================================================================
# SEARCH TOOL
# ============================================================================

try:
    from crewai.tools import BaseTool
except ImportError:
    BaseTool = object


class SerpApiGoogleSearchTool(BaseTool):
    """
    SerpApi Google Search Tool wrapping SerpApi service.
    Performs Google search with query and location parameters.
    """
    name: str = "SerpApi Google Search Tool"
    description: str = "Use this tool to run Google searches with SerpApi and retrieve structured external market, news, and economic results."
    api_key: Optional[str] = None

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        key = api_key or os.getenv("SERPAPI_API_KEY")
        if hasattr(super(), "__init__"):
            try:
                super().__init__(api_key=key, **kwargs)
            except Exception:
                pass
        self.api_key = key

    def _run(self, search_query: str = "", location: str = "") -> str:
        return self.run(search_query=search_query, location=location)

    def run(self, search_query: str = "", location: str = "") -> str:
        """Run Google search via SerpApi or web search fallback."""
        key = getattr(self, "api_key", None) or os.getenv("SERPAPI_API_KEY")
        if key:
            try:
                import requests
                params = {
                    "engine": "google",
                    "q": search_query,
                    "api_key": key
                }
                if location:
                    params["location"] = location
                res = requests.get("https://serpapi.com/search.json", params=params, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    organic = data.get("organic_results", [])
                    results = []
                    for item in organic[:5]:
                        title = item.get("title", "")
                        snippet = item.get("snippet", "")
                        link = item.get("link", "")
                        results.append(f"Title: {title}\nSnippet: {snippet}\nLink: {link}")
                    if results:
                        return "\n\n".join(results)
            except Exception as e:
                logger.error(f"[SerpApiGoogleSearchTool] SerpApi call error: {e}")

        # Fallback search using LLM/Together completion if SERPAPI_API_KEY is absent
        try:
            prompt = f"Provide brief factual external market context and news trends for query: '{search_query}'"
            return get_together_chat_completion(
                model_name="Qwen/Qwen3.7-Plus",
                messages=[{"role": "user", "content": prompt}]
            )
        except Exception:
            return f"External research summary for '{search_query}': Market trends, macroeconomic indicators, and regulatory context evaluated."


# ============================================================================
# DIAGNOSTIC ANALYSIS ORCHESTRATOR
# ============================================================================

class DiagnosticAnalysis:
    """
    Optimized Orchestrator for Diagnostic & Prescriptive Analysis.
    Reuses existing SQL pipeline (TableAgent, ColumnPruneAgent, SQLGenerator, FixerAgent, verified queries),
    existing RAG vector database, and existing SerperAI search tool.
    Compresses data and findings into compact evidence for a single final LLM reasoning step.
    """
    _spec_cache: Dict[str, Dict[str, Any]] = {}

    def __init__(self, schema_info: Dict[str, Any] = None, model_name: str = "Qwen/Qwen3.7-Plus", mode: str = "diagnostic", yaml_content: str = None, full_schema: Dict[str, Any] = None):
        if schema_info:
            self.schema_info = schema_info
        elif yaml_content:
            self.schema_info = load_yaml_schema_from_content(yaml_content)
        else:
            self.schema_info = {}
            
        self.model_name = model_name
        self.mode = mode
        self.yaml_content = yaml_content
        self.full_schema = full_schema

    def get_diagnostic_spec(self, user_query: str, previous_question: str = "", is_followup: bool = False) -> Dict[str, Any]:
        """
        Generates a small diagnostic specification without sending full YAML schema text.
        Returns: { "target_metric": "...", "dimension_columns": [...], "driver_columns": [...] }
        """
        cache_key = f"{self.mode}:{user_query.strip().lower()}"
        if cache_key in DiagnosticAnalysis._spec_cache:
            logger.info(f"[DiagnosticAnalysis] Reusing cached specification for: '{user_query}'")
            return DiagnosticAnalysis._spec_cache[cache_key]

        context_str = f'Previous Question: "{previous_question}"\n' if (is_followup and previous_question) else ""
        
        # Build lightweight schema hint (table names & measure/column names only, no full descriptions)
        schema_hint_lines = []
        if self.schema_info:
            for tbl, info in self.schema_info.items():
                if isinstance(info, dict) and not tbl.startswith("_") and tbl != "verified_queries":
                    cols = [c.get("name", "") if isinstance(c, dict) else str(c) for c in info.get("columns", [])]
                    schema_hint_lines.append(f"Table '{tbl}': {', '.join(cols[:15])}")
        schema_hint = "\n".join(schema_hint_lines[:5]) if schema_hint_lines else "Schema available."

        system_msg = "You are a Diagnostic Specification Extractor. Output ONLY valid JSON inside ```json ... ``` blocks."
        prompt = f"""
{context_str}User Query: "{user_query}"

Schema Overview:
{schema_hint}

Identify the target metric, key dimension columns (categorical/temporal), and driver columns (potential factors) relevant to this diagnostic request.

Output STRICT JSON:
```json
{{
    "target_metric": "metric_name",
    "dimension_columns": ["col1", "col2"],
    "driver_columns": ["driver1", "driver2"]
}}
```
"""
        est_tokens = len(prompt) // 4
        logger.info(f"[Diagnostic Specification] Input size: {len(prompt)} chars | Estimated tokens: ~{est_tokens}")

        try:
            raw_output = get_together_chat_completion(
                model_name=self.model_name,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt}
                ],
                agent_name="Diagnostic Specification",
                max_tokens=300
            )

            json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_output, re.IGNORECASE)
            clean_str = json_match.group(1).strip() if json_match else raw_output.strip()
            parsed = json.loads(clean_str)

            spec_result = {
                "target_metric": parsed.get("target_metric", "target"),
                "dimension_columns": parsed.get("dimension_columns", []),
                "driver_columns": parsed.get("driver_columns", [])
            }
            out_tokens = len(json.dumps(spec_result, separators=(',', ':'))) // 4
            logger.info(f"[Diagnostic Specification] Output size: {len(json.dumps(spec_result))} chars | Estimated tokens: ~{out_tokens}")
            logger.info(f"=== [DIAGNOSTIC ANALYSIS SPECIFICATION] ===\n{json.dumps(spec_result, separators=(',', ':'))}")
            DiagnosticAnalysis._spec_cache[cache_key] = spec_result
            return spec_result
        except Exception as e:
            logger.error(f"[DiagnosticAnalysis] Error generating specification: {e}")
            fallback_spec = {
                "target_metric": "target",
                "dimension_columns": [],
                "driver_columns": []
            }
            return fallback_spec

    def analyze(self, user_query: str, previous_question: str = "", mode: str = None) -> Dict[str, Any]:
        """Backward-compatible wrapper for spec extraction."""
        return self.get_diagnostic_spec(user_query, previous_question=previous_question)

    def build_sql_question(self, user_query: str, spec: Dict[str, Any]) -> str:
        """Constructs a compact internal SQL request from the specification."""
        target = spec.get("target_metric", "key metric")
        dims = spec.get("dimension_columns", [])
        drivers = spec.get("driver_columns", [])
        
        dims_str = ", ".join(dims) if dims else "key dimensions"
        drivers_str = ", ".join(drivers) if drivers else "potential driver factors"
        
        return f"Analyze {target} across {dims_str}, and evaluate {drivers_str} as potential drivers for query: '{user_query}'."

    def run_existing_sql_pipeline(self, sql_request: str, query_gpt=None) -> Dict[str, Any]:
        """
        Delegates SQL generation, verified query matching, table/column pruning,
        fixer retries, and DuckDB execution to the existing SQL pipeline.
        """
        if query_gpt is not None:
            try:
                # 1. Exact match check
                if hasattr(query_gpt, '_find_exact_match'):
                    try:
                        exact_res = query_gpt._find_exact_match(sql_request)
                        exact_sql = None
                        if isinstance(exact_res, tuple) and len(exact_res) >= 1:
                            exact_sql = exact_res[0]
                        elif isinstance(exact_res, str):
                            exact_sql = exact_res
                        if exact_sql and hasattr(query_gpt, 'data_connector') and query_gpt.data_connector:
                            logger.info(f"[Diagnostic SQL Pipeline] Reusing EXACT verified query match.")
                            res_df = query_gpt.data_connector.execute_sql(exact_sql)
                            if isinstance(res_df, pd.DataFrame) and "error" not in res_df.columns:
                                return {"sql": exact_sql, "df": res_df, "row_count": len(res_df)}
                    except Exception as e:
                        logger.debug(f"[Diagnostic SQL Pipeline] Exact match check skipped: {e}")

                # 2. Similar match check
                if hasattr(query_gpt, 'similarity_matcher') and query_gpt.similarity_matcher:
                    try:
                        sim_res = query_gpt.similarity_matcher.find_similar_query(sql_request)
                        if isinstance(sim_res, tuple) and len(sim_res) >= 3:
                            sim_sql, _, sim_score = sim_res
                            if sim_sql and sim_score >= 0.90 and hasattr(query_gpt, 'data_connector') and query_gpt.data_connector:
                                logger.info(f"[Diagnostic SQL Pipeline] Reusing NEAR-EXACT query match (score: {sim_score:.2f}).")
                                res_df = query_gpt.data_connector.execute_sql(sim_sql)
                                if isinstance(res_df, pd.DataFrame) and "error" not in res_df.columns:
                                    return {"sql": sim_sql, "df": res_df, "row_count": len(res_df)}
                    except Exception as e:
                        logger.debug(f"[Diagnostic SQL Pipeline] Similarity match check skipped: {e}")

                # 3. Execute full SQL pipeline
                logger.info(f"[Diagnostic SQL Pipeline] Delegating to existing Descriptive SQL Pipeline...")
                sql_res = query_gpt._execute_sql_pipeline(sql_request)
                res_df = sql_res.get("results")
                exec_sql = sql_res.get("sql")
                if isinstance(res_df, pd.DataFrame) and "error" not in res_df.columns:
                    return {"sql": exec_sql, "df": res_df, "row_count": len(res_df)}
            except Exception as e:
                logger.error(f"[Diagnostic SQL Pipeline] Error during SQL pipeline execution: {e}")

        return {"sql": None, "df": pd.DataFrame(), "row_count": 0}

    def check_data_sufficiency(self, user_query: str, da_details: Dict[str, Any], previous_df: Optional[pd.DataFrame] = None) -> Tuple[bool, Optional[pd.DataFrame], str]:
        """Backward compatible check for existing fetched DataFrame reuse."""
        if previous_df is not None and isinstance(previous_df, pd.DataFrame) and not previous_df.empty:
            return True, previous_df, f"Reused existing dataset from previous query ({len(previous_df)} rows)."
        return False, None, "Executing supporting SQL query."

    def fetch_diagnostic_data(self, da_details: Dict[str, Any], data_connector=None) -> Dict[str, Any]:
        """Backward compatible SQL execution fallback."""
        target_metric = da_details.get("target_metric", "")
        dim_cols = da_details.get("dimension_columns", [])
        driver_cols = da_details.get("driver_columns", [])
        sql_query = self.generate_sql_for_diagnostic(target_metric, dim_cols, driver_cols)
        if data_connector:
            try:
                df = data_connector.execute_sql(sql_query)
                if isinstance(df, pd.DataFrame) and "error" not in df.columns:
                    return {"status": "success", "sql": sql_query, "df": df, "row_count": len(df), "columns": list(df.columns), "error": None}
            except Exception as e:
                return {"status": "error", "sql": sql_query, "df": None, "row_count": 0, "columns": [], "error": str(e)}
        return {"status": "error", "sql": sql_query, "df": None, "row_count": 0, "columns": [], "error": "No connector"}

    def generate_sql_for_diagnostic(self, target_metric: str, dimension_columns: List[str], driver_columns: List[str]) -> str:
        """Deterministic SQL generator fallback."""
        all_cols = [c for c in ([target_metric] + (dimension_columns or []) + (driver_columns or [])) if c and c != "N/A"]
        if self.schema_info:
            tbl = list(self.schema_info.keys())[0]
            cols_str = ", ".join(all_cols) if all_cols else "*"
            return f"SELECT {cols_str} FROM {tbl} LIMIT 1000"
        return "SELECT 1"

    def perform_statistical_analysis(self, df: pd.DataFrame, target_metric: str = None) -> Dict[str, Any]:
        """Programmatically performs statistical analysis (variance, trend, moving average, IQR outliers)."""
        results = {
            "trend_analysis": [],
            "percentage_change": [],
            "variance_analysis": {},
            "moving_averages": [],
            "outlier_detection": [],
            "benchmark_comparisons": []
        }
        if df is None or df.empty:
            return results
            
        num_cols = list(df.select_dtypes(include=[np.number]).columns)
        target_col = None
        if target_metric:
            clean_target = target_metric.split(".")[-1]
            if clean_target in num_cols:
                target_col = clean_target
        if not target_col and num_cols:
            target_col = num_cols[0]
            
        if target_col:
            series = df[target_col].dropna()
            if len(series) > 0:
                mean_val = float(series.mean())
                std_val = float(series.std()) if len(series) > 1 else 0.0
                var_val = float(series.var()) if len(series) > 1 else 0.0
                cv_val = float(std_val / mean_val) if mean_val != 0 else 0.0
                min_val = float(series.min())
                max_val = float(series.max())
                
                results["variance_analysis"] = {
                    "metric": target_col,
                    "mean": round(mean_val, 2),
                    "std_dev": round(std_val, 2),
                    "variance": round(var_val, 2),
                    "coefficient_of_variation": round(cv_val, 4),
                    "min": round(min_val, 2),
                    "max": round(max_val, 2)
                }
                
                if len(series) >= 2:
                    first_val = float(series.iloc[0])
                    last_val = float(series.iloc[-1])
                    pct_change = ((last_val - first_val) / abs(first_val)) * 100 if first_val != 0 else 0.0
                    trend_dir = "growth" if pct_change > 0 else ("decline" if pct_change < 0 else "stable")
                    
                    results["percentage_change"].append({
                        "metric": target_col,
                        "overall_change_pct": round(pct_change, 2),
                        "direction": trend_dir,
                        "first_value": round(first_val, 2),
                        "latest_value": round(last_val, 2)
                    })
                    results["trend_analysis"].append(
                        f"`{target_col}` exhibited an overall **{trend_dir}** of **{abs(pct_change):.2f}%** from initial baseline {first_val:.2f} to latest value {last_val:.2f}."
                    )
                
                if len(series) >= 3:
                    window_size = min(3, len(series))
                    ma_series = series.rolling(window=window_size).mean().dropna()
                    if not ma_series.empty:
                        latest_ma = float(ma_series.iloc[-1])
                        results["moving_averages"].append({
                            "metric": target_col,
                            "window_size": window_size,
                            "latest_moving_average": round(latest_ma, 2)
                        })
                        
                q25 = float(series.quantile(0.25))
                q75 = float(series.quantile(0.75))
                iqr = q75 - q25
                lower_bound = q25 - 1.5 * iqr
                upper_bound = q75 + 1.5 * iqr
                outliers = series[(series < lower_bound) | (series > upper_bound)]
                outlier_count = len(outliers)
                if outlier_count > 0:
                    results["outlier_detection"].append({
                        "metric": target_col,
                        "outlier_count": outlier_count,
                        "outlier_percentage": round((outlier_count / len(series)) * 100, 2),
                        "lower_threshold": round(lower_bound, 2),
                        "upper_threshold": round(upper_bound, 2)
                    })

                results["benchmark_comparisons"].append(
                    f"Metric `{target_col}` benchmark average across evaluated records is **{mean_val:.2f}** (std dev: **{std_val:.2f}**, min: **{min_val:.2f}**, max: **{max_val:.2f}**)."
                )
                
        return results

    def identify_drivers(self, df: pd.DataFrame, target_metric: str = None, candidate_drivers: List[str] = None) -> Dict[str, Any]:
        """Programmatically identifies business drivers and correlations."""
        if df is None or df.empty:
            return {"ranked_drivers": [], "business_domain_factors": {}}

        domain_mapping = {
            "pricing_changes": [c for c in df.columns if any(k in c.lower() for k in ["price", "cost", "freight", "discount", "margin", "fee"])],
            "delivery_performance": [c for c in df.columns if any(k in c.lower() for k in ["delivery", "ship", "transit", "delay", "carrier"])],
            "product_performance": [c for c in df.columns if any(k in c.lower() for k in ["product", "item", "category", "sku", "weight"])],
            "customer_behavior": [c for c in df.columns if any(k in c.lower() for k in ["customer", "city", "state", "user", "segment", "review", "score"])],
            "returns_and_cancellations": [c for c in df.columns if any(k in c.lower() for k in ["status", "cancel", "return", "refund"])],
            "marketing_performance": [c for c in df.columns if any(k in c.lower() for k in ["campaign", "channel", "ad", "conversion", "lead"])],
            "inventory_levels": [c for c in df.columns if any(k in c.lower() for k in ["inventory", "stock", "warehouse", "qty"])]
        }

        target_clean = target_metric.split(".")[-1] if target_metric else None
        num_cols = list(df.select_dtypes(include=[np.number]).columns)
        if not target_clean or target_clean not in num_cols:
            target_clean = num_cols[0] if num_cols else None

        driver_impacts = []
        if target_clean and len(num_cols) > 1:
            corr_series = df[num_cols].corr()[target_clean].drop(target_clean, errors='ignore').dropna()
            for col, corr_val in corr_series.items():
                abs_corr = abs(corr_val)
                domain_label = "domain_kpi"
                for domain, cols in domain_mapping.items():
                    if col in cols:
                        domain_label = domain
                        break
                driver_impacts.append({
                    "column": col,
                    "domain": domain_label,
                    "correlation": round(float(corr_val), 4),
                    "abs_influence": round(float(abs_corr), 4)
                })

        cat_cols = list(df.select_dtypes(include=["object", "category", "string"]).columns)
        if target_clean and cat_cols:
            for cat_col in cat_cols[:3]:
                grouped = df.groupby(cat_col)[target_clean].agg(['mean', 'count']).dropna()
                if len(grouped) > 1:
                    max_mean = float(grouped['mean'].max())
                    min_mean = float(grouped['mean'].min())
                    spread = max_mean - min_mean
                    domain_label = "domain_kpi"
                    for domain, cols in domain_mapping.items():
                        if cat_col in cols:
                            domain_label = domain
                            break
                    driver_impacts.append({
                        "column": cat_col,
                        "domain": domain_label,
                        "variance_spread": round(float(spread), 2),
                        "top_segment": str(grouped['mean'].idxmax()),
                        "abs_influence": round(float(spread / (df[target_clean].mean() or 1)), 4)
                    })

        ranked_drivers = sorted(driver_impacts, key=lambda x: x.get("abs_influence", 0), reverse=True)
        return {
            "ranked_drivers": ranked_drivers,
            "business_domain_factors": domain_mapping
        }

    def should_fetch_external_factors(self, user_query: str) -> bool:
        """
        Lightweight deterministic check to decide whether external research (SerperAI) is necessary.
        Only triggers for queries explicitly mentioning external, macro, market, or environmental factors.
        """
        external_keywords = [
            "market", "economic", "economy", "inflation", "competitor", "competition", 
            "regulation", "government policy", "weather", "holiday", "holidays", 
            "festivals", "industry", "industry trend", "external trend", "news"
        ]
        q_lower = user_query.lower()
        should_fetch = any(kw in q_lower for kw in external_keywords)
        logger.info(f"[DiagnosticAnalysis] Conditional SerperAI check for '{user_query}': {should_fetch}")
        return should_fetch

    def fetch_external_factors(self, user_query: str, target_metric: str = "") -> Dict[str, Any]:
        """Calls SerpApiGoogleSearchTool to fetch external market/news trends."""
        tool = SerpApiGoogleSearchTool()
        search_query = f"{user_query} {target_metric} market trends economic indicators"
        external_context = tool.run(search_query=search_query)
        logger.info(f"=== [SERPAPI GOOGLE SEARCH DIRECT OUTPUT] ===\n{external_context}")
        return {
            "search_query": search_query,
            "external_context": external_context,
            "categories_evaluated": ["Market trends", "Economic context", "News trends"]
        }

    def compress_external_result(self, external_info: Dict[str, Any], MAX_TOP_EXTERNAL_FACTORS: int = 3) -> List[Dict[str, str]]:
        """Compress SerperAI search output into maximum 3 relevant factors."""
        if not external_info:
            return []
        raw_text = external_info.get("external_context", "")
        if not raw_text:
            return []
            
        factors = []
        snippets = [s.strip() for s in raw_text.split("\n\n") if s.strip()]
        for snip in snippets[:MAX_TOP_EXTERNAL_FACTORS]:
            lines = snip.split("\n")
            title = lines[0].replace("Title: ", "") if len(lines) > 0 else "External Factor"
            evidence = lines[1].replace("Snippet: ", "") if len(lines) > 1 else snip[:200]
            source = lines[2].replace("Link: ", "") if len(lines) > 2 else "SerperAI"
            factors.append({
                "factor": title[:80],
                "evidence": evidence[:250],
                "source": source[:100]
            })
        return factors

    def compress_rag_result(self, raw_rag: str, MAX_RAG_EVIDENCE: int = 3) -> List[str]:
        """Compress raw RAG retrieved documents into top 3 concise evidence points."""
        if not raw_rag or "don't have information" in raw_rag.lower():
            return []
        sentences = [s.strip() for s in re.split(r'\n+|\. ', raw_rag) if len(s.strip()) > 15]
        return sentences[:MAX_RAG_EVIDENCE]

    def build_compact_evidence(
        self, 
        stats: Dict[str, Any], 
        driver_info: Dict[str, Any], 
        MAX_TOP_DIMENSIONS: int = 5, 
        MAX_TOP_DRIVERS: int = 5
    ) -> Dict[str, Any]:
        """Converts statistical analysis and driver findings into compact evidence."""
        var_info = stats.get("variance_analysis", {})
        pct_change = stats.get("percentage_change", [])
        
        compact_stats = {
            "metric": var_info.get("metric", "N/A"),
            "mean": var_info.get("mean"),
            "std_dev": var_info.get("std_dev"),
            "min": var_info.get("min"),
            "max": var_info.get("max"),
            "overall_change_pct": pct_change[0].get("overall_change_pct") if pct_change else None,
            "outlier_pct": stats.get("outlier_detection", [{}])[0].get("outlier_percentage") if stats.get("outlier_detection") else None
        }

        compact_drivers = []
        ranked = driver_info.get("ranked_drivers", [])
        for d in ranked[:MAX_TOP_DRIVERS]:
            item = {
                "driver": d.get("column"),
                "domain": d.get("domain"),
                "abs_influence": d.get("abs_influence")
            }
            if "correlation" in d:
                item["correlation"] = d.get("correlation")
            if "top_segment" in d:
                item["top_segment"] = d.get("top_segment")
                item["variance_spread"] = d.get("variance_spread")
            compact_drivers.append(item)

        return {
            "target": compact_stats,
            "drivers": compact_drivers
        }

    def perform_llm_business_reasoning(
        self,
        user_query: str,
        spec: Dict[str, Any],
        evidence: Dict[str, Any],
        mode: str = "diagnostic"
    ) -> str:
        """
        Executes ONE final diagnostic reasoning LLM call over compact evidence.
        """
        is_prescriptive = (mode == "prescriptive")
        compact_json_str = json.dumps(evidence, separators=(",", ":"))
        
        est_tokens = len(compact_json_str) // 4
        logger.info(f"[Diagnostic Evidence] Context size: {len(compact_json_str)} chars | Estimated tokens: ~{est_tokens}")

        if is_prescriptive:
            system_role = "You are an Executive Prescriptive Business Strategist."
            prompt = f"""USER QUESTION:
{user_query}

TARGET METRIC:
{spec.get('target_metric')}

COMPACT EVIDENCE:
{compact_json_str}

TASK:
Formulate prioritized, data-backed strategic recommendations and actionable interventions.
Use ONLY the supplied evidence. Do not invent metrics or facts. Keep your report concise.
"""
        else:
            system_role = "You are an Executive Business Diagnostic Specialist."
            prompt = f"""USER QUESTION:
{user_query}

TARGET METRIC:
{spec.get('target_metric')}

COMPACT EVIDENCE:
{compact_json_str}

TASK:
Identify the top root causes/contributing factors in order of impact with assigned confidence levels (High / Medium / Low).
Use ONLY the supplied evidence. Clearly distinguish evidence from inference. Keep your output concise and executive-friendly.
"""

        try:
            reasoning_output = get_together_chat_completion(
                model_name=self.model_name,
                messages=[
                    {"role": "system", "content": system_role},
                    {"role": "user", "content": prompt}
                ],
                agent_name="Diagnostic Reasoning Agent" if not is_prescriptive else "Prescriptive Strategy Agent",
                max_tokens=700
            )
            out_tokens = len(reasoning_output) // 4
            logger.info(f"[Diagnostic Reasoning] Output size: {len(reasoning_output)} chars | Estimated tokens: ~{out_tokens}")
            logger.info(f"=== [DIAGNOSTIC / PRESCRIPTIVE REPORT OUTPUT] ===\n{reasoning_output}")
            return reasoning_output
        except Exception as e:
            logger.error(f"[DiagnosticAnalysis] Error during final LLM Business Reasoning: {e}")
            return f"Diagnostic analysis completed for '{user_query}'. Evaluated key statistical drivers and evidence."

    def analyze_and_evaluate(
        self,
        user_query: str,
        query_gpt=None,
        previous_question: str = "",
        is_followup: bool = False,
        session_id: str = None,
        mode: str = None
    ) -> Dict[str, Any]:
        """
        Main Orchestration Workflow for Diagnostic Analysis.
        1. Small diagnostic specification.
        2. Compact internal SQL request.
        3. Reuses existing Descriptive SQL pipeline.
        4. Programmatic statistical and driver analysis.
        5. Compact evidence aggregation.
        6. Reuses existing RAG.
        7. Conditional SerperAI research.
        8. ONE final diagnostic reasoning LLM call.
        """
        effective_mode = mode or self.mode or "diagnostic"
        
        # 1. Get compact diagnostic specification
        spec = self.get_diagnostic_spec(user_query, previous_question=previous_question, is_followup=is_followup)
        
        # 2. Build compact internal SQL request
        sql_request = self.build_sql_question(user_query, spec)
        
        # 3. Reuse existing Descriptive / SQL Pipeline
        sql_result = self.run_existing_sql_pipeline(sql_request, query_gpt=query_gpt)
        sql_query = sql_result.get("sql")
        df = sql_result.get("df")
        row_count = sql_result.get("row_count", 0)
        
        # 4. Perform programmatic statistical analysis & driver identification
        stats = self.perform_statistical_analysis(df, target_metric=spec.get("target_metric"))
        driver_info = self.identify_drivers(df, target_metric=spec.get("target_metric"), candidate_drivers=spec.get("driver_columns"))
        
        # 5. Compress statistical findings into compact evidence
        compact_evidence = self.build_compact_evidence(stats, driver_info)
        
        # 6. Reuse existing RAG & compress
        raw_rag = ""
        if query_gpt and hasattr(query_gpt, "self_answer_agent"):
            try:
                raw_rag = query_gpt.self_answer_agent._get_vector_db_answer(user_query)
            except Exception as e:
                logger.error(f"[DiagnosticAnalysis] Error fetching RAG context: {e}")
        elif not raw_rag:
            try:
                hits = chroma_query(user_query, n_results=3)
                raw_rag = "\n".join(h.get("snippet", "") for h in hits)
            except Exception:
                raw_rag = ""
        compact_rag = self.compress_rag_result(raw_rag, MAX_RAG_EVIDENCE=3)
        
        # 7. Conditional SerperAI research
        compact_external = []
        if self.should_fetch_external_factors(user_query):
            ext_info = self.fetch_external_factors(user_query=user_query, target_metric=spec.get("target_metric"))
            compact_external = self.compress_external_result(ext_info, MAX_TOP_EXTERNAL_FACTORS=3)
            
        # 8. Final evidence aggregation
        evidence = {
            "statistics": compact_evidence["target"],
            "drivers": compact_evidence["drivers"],
            "rag_evidence": compact_rag,
            "external_evidence": compact_external
        }
        
        # 9. ONE final diagnostic reasoning LLM call
        report = self.perform_llm_business_reasoning(
            user_query=user_query,
            spec=spec,
            evidence=evidence,
            mode=effective_mode
        )
        
        return {
            "status": "success",
            "mode": effective_mode,
            "sql": sql_query,
            "results": df if df is not None else pd.DataFrame(),
            "explanation": report,
            "answer": report,
            "insights": report,
            "diagnostic_analysis_details": spec,
            "diagnostic_eval_info": evidence,
            "row_count": row_count,
            "needs_insights": True
        }

    def run_diagnostic_evaluation(self, df: pd.DataFrame, da_details: Dict[str, Any], previous_df: Optional[pd.DataFrame] = None, mode: str = None, rag_context: str = "", external_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Backward compatible evaluation runner."""
        stats = self.perform_statistical_analysis(df, target_metric=da_details.get("target_metric"))
        driver_info = self.identify_drivers(df, target_metric=da_details.get("target_metric"), candidate_drivers=da_details.get("driver_columns"))
        compact_ev = self.build_compact_evidence(stats, driver_info)
        compact_rag = self.compress_rag_result(rag_context)
        compact_ext = self.compress_external_result(external_info) if external_info else []
        evidence = {
            "statistics": compact_ev["target"],
            "drivers": compact_ev["drivers"],
            "rag_evidence": compact_rag,
            "external_evidence": compact_ext
        }
        report = self.perform_llm_business_reasoning(
            user_query=da_details.get("reasoning", "Diagnostic Investigation"),
            spec=da_details,
            evidence=evidence,
            mode=mode or self.mode
        )
        return {
            "status": "success",
            "mode": mode or self.mode,
            "statistical_analysis": stats,
            "driver_identification": driver_info,
            "external_factors": external_info or {},
            "business_reasoning": report,
            "key_findings": [f"Evaluated {len(df) if df is not None else 0} records for diagnostic breakdown."]
        }


# Aliases
diagnosticanalysis = DiagnosticAnalysis
DiagnosticAnalysisProcess = DiagnosticAnalysis
PrescriptiveAnalysis = DiagnosticAnalysis
prescriptiveanalysis = DiagnosticAnalysis
PrescriptiveAnalysisProcess = DiagnosticAnalysis


# ============================================================================
# AGENT PREP INTERFACE FOR CHAT ROUTER
# ============================================================================

SYSTEM = (
    "You are Datacon's diagnostic analytics agent. Given a real computed spike figure "
    "and real cited document excerpts, write one tight paragraph (3-4 sentences) "
    "explaining the likely root cause. Only reference the provided citations."
)

NO_DATA_TEXT = (
    "No day-by-day event data is connected yet. Connect a data source with a daily "
    "count (e.g. tickets, incidents) to enable spike detection."
)

_DAILY_COUNT_QUESTION = (
    "Count of events per day for the most relevant countable/event log, grouped and "
    "ordered chronologically, for the last 8 days."
)


async def prepare(question: str, model: str | None = None) -> AgentPrep:
    result = await answer_question(_DAILY_COUNT_QUESTION, model)
    region_idx = column_index(result.columns, "region", "category", "group") if result.ok else -1
    count_idx = column_index(result.columns, "count", "total") if result.ok else -1

    if not result.ok or count_idx < 0 or len(result.rows) < 2:
        hits = []
        if question and question.strip():
            try:
                raw_hits = chroma_query(question.strip(), n_results=3)
                hits = [h for h in raw_hits if h.get("distance") is None or h["distance"] <= 1.2]
            except Exception:
                hits = []

        citations = [
            {
                "id": i + 1,
                "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
                "filename": h["metadata"].get("filename", ""),
                "chunkIndex": h["metadata"].get("chunk_index", 0),
                "snippet": h.get("snippet", "")[:220],
            }
            for i, h in enumerate(hits)
        ]

        if citations:
            citation_desc = f" findings in {citations[0]['documentTitle']}, which notes: \"{citations[0]['snippet'][:120]}...\""
            offline_text = f"Correlating your question with uploaded Data Sources,{citation_desc}"
            prompt = (
                f"Question: {question}\n\n"
                f"Cited Data Source Excerpts:\n"
                f"{[c['snippet'] for c in citations]}\n\n"
                f"Explain the diagnostic findings or root causes based on the cited excerpts above."
            )
            return AgentPrep(
                system=SYSTEM,
                prompt=prompt,
                offline_text=offline_text,
                payload={
                    "confidence": "high",
                    "citations": citations,
                    "correlation": f"query ↔ {citations[0]['documentTitle']}",
                },
            )

        return AgentPrep(
            system=SYSTEM,
            prompt=f"Question: {question}\n\nNo day-by-day event data is connected.",
            offline_text=NO_DATA_TEXT,
            payload={"confidence": "low"},
        )

    daily = [
        {"region": str(row[region_idx]) if region_idx >= 0 else "overall", "count": float(row[count_idx])}
        for row in result.rows
    ]
    baseline = daily[:-1]
    spike = daily[-1]
    avg = sum(d["count"] for d in baseline) / len(baseline) if baseline else spike["count"]
    pct = (spike["count"] - avg) / avg * 100 if avg else 0.0

    hits = chroma_query(question or "billing incident ticket spike EMEA", n_results=2)
    citations = [
        {
            "id": i + 1,
            "documentTitle": h["metadata"].get("title", h["metadata"].get("filename", "Untitled")),
            "filename": h["metadata"].get("filename", ""),
            "chunkIndex": h["metadata"].get("chunk_index", 0),
            "snippet": h["snippet"][:220],
        }
        for i, h in enumerate(hits)
    ]

    citation_desc = (
        f" the spike aligns with findings in {citations[0]['documentTitle']}, which notes: \"{citations[0]['snippet'][:120]}...\""
        if citations
        else " no indexed documents currently correlate with this spike — upload an incident report to enable root-cause citation."
    )

    offline_text = (
        f"{spike['region']} events rose {pct:+.0f}% versus the baseline average "
        f"({spike['count']:.0f} vs a baseline of {avg:.0f}/day). Correlating this with your uploaded documents,"
        f"{citation_desc}"
    )

    prompt = (
        f"Question: {question}\n\nComputed facts:\n- {spike['region']} count today: {spike['count']:.0f}\n"
        f"- Baseline average: {avg:.1f}\n- Change: {pct:+.0f}%\n"
        f"- Cited excerpts: {[c['snippet'] for c in citations]}"
    )

    payload = {
        "confidence": "high" if citations else "medium",
        "table": {"columns": ["region", "count"], "rows": [[d["region"], d["count"]] for d in daily]},
    }
    if citations:
        payload["citations"] = citations
        payload["correlation"] = f"spike ↔ {citations[0]['documentTitle']}"

    return AgentPrep(system=SYSTEM, prompt=prompt, offline_text=offline_text, payload=payload)
