"""Semantic model YAML generation for connectors and data sources (CSV/XLSX).

Generates rich semantic metadata including:
- Inferred column data types (INTEGER, FLOAT, BOOLEAN, TIMESTAMP, VARCHAR, etc.)
- Primary key candidate inference (single and composite)
- Cross-table foreign key relationship detection with confidence & cardinality
- Sample values and column descriptions
- Standardized YAML serialization saved to data storage directory
"""
import io
import itertools
import logging
import math
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

from app.config import settings

logger = logging.getLogger("app.query_engine.semantic_model")


def looks_like_numeric(val: Any) -> bool:
    """Check if a value looks like a numeric value."""
    if val is None:
        return False
    v = str(val).strip()
    if v == "":
        return False
    v = v.replace(",", "")
    numeric_regex = re.compile(r"^[+-]?(\d+(\.\d+)?|\.\d+)$")
    return bool(numeric_regex.match(v))


def has_content(obj: Any) -> bool:
    """Check if an object has meaningful content."""
    if obj is None:
        return False
    if isinstance(obj, np.ndarray):
        return obj.size > 0
    if isinstance(obj, (list, tuple)):
        return len(obj) > 0
    if hasattr(obj, "empty") and not obj.empty:
        return True
    try:
        return bool(len(obj) > 0)
    except Exception:
        try:
            return bool(obj)
        except Exception:
            return False


def _first_nonempty_samples(series: pd.Series, n: int = 5) -> List[str]:
    """Get first non-empty string samples from a pandas Series."""
    vals = series.dropna().astype(str)
    vals = vals[vals.str.strip() != ""]
    return vals.head(n).tolist()


def infer_column_type_from_samples(samples: list, pandas_series: pd.Series) -> str:
    """Infer SQL column type from sample values and series dtype."""
    clean_samples = [str(s).strip() for s in samples if s is not None and str(s).strip() != ""]
    pd_type = str(pandas_series.dtype).lower()

    if len(clean_samples) == 0:
        if "int" in pd_type:
            return "INTEGER"
        if "float" in pd_type or "double" in pd_type:
            return "FLOAT"
        if "bool" in pd_type:
            return "BOOLEAN"
        if "datetime" in pd_type or "timestamp" in pd_type:
            return "TIMESTAMP"
        if "date" in pd_type:
            return "DATE"
        return "VARCHAR"

    numeric_count = sum(1 for s in clean_samples if looks_like_numeric(s))
    bool_count = sum(1 for s in clean_samples if str(s).lower() in ("true", "false", "0", "1"))

    if numeric_count / len(clean_samples) >= 0.8:
        has_decimal = any("." in s for s in clean_samples if looks_like_numeric(s))
        return "FLOAT" if has_decimal else "INTEGER"

    if bool_count / len(clean_samples) >= 0.8:
        return "BOOLEAN"

    # Date parsing check
    date_count = 0
    non_numeric_samples = [s for s in clean_samples if not looks_like_numeric(s)]
    for s in non_numeric_samples:
        try:
            # Use pandas to_datetime with strict format parsing
            res = pd.to_datetime(s, errors="coerce")
            if pd.notna(res):
                date_count += 1
        except Exception:
            pass

    if len(non_numeric_samples) > 0 and (date_count / len(non_numeric_samples)) >= 0.7:
        return "TIMESTAMP"

    if "datetime" in pd_type or "timestamp" in pd_type:
        return "TIMESTAMP"

    return "VARCHAR"


def _make_column_entry(col_name: str, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Create a column entry for the semantic model."""
    sql_type = "VARCHAR"
    pandas_type = ""
    nullable = True
    sample_values = []

    if df is not None and col_name in df.columns:
        col = df[col_name]
        pandas_type = str(col.dtype)
        nullable = bool(col.isnull().any())
        sample_values = _first_nonempty_samples(col, n=5)
        sql_type = infer_column_type_from_samples(sample_values, col)

    return {
        "name": col_name,
        "type": sql_type,
        "pandas_type": pandas_type,
        "nullable": nullable,
        "sample_values": sample_values,
        "description": f"Column '{col_name}'",
    }


def infer_primary_keys(
    df: pd.DataFrame,
    max_composite: int = 2,
    uniqueness_threshold: float = 0.98,
    null_threshold: float = 0.02,
    max_rows_check: int = 1000,
) -> List[Any]:
    """Infer primary key candidates from a DataFrame with fast vectorization."""
    candidates = []
    if df.shape[0] == 0:
        return candidates

    sample = df.head(max_rows_check)
    n = len(sample)
    if n == 0:
        return candidates

    for col in sample.columns:
        s = sample[col]
        non_null = s.dropna()
        if len(non_null) == 0:
            continue
        unique_count = non_null.nunique(dropna=True)
        null_fraction = 1 - (len(non_null) / n)
        unique_fraction = unique_count / len(non_null)
        if unique_fraction >= uniqueness_threshold and null_fraction <= null_threshold:
            candidates.append((col,))

    cols = list(sample.columns)
    if max_composite >= 2 and len(cols) >= 2:
        for r in range(2, min(max_composite, len(cols)) + 1):
            for combo in itertools.combinations(cols[:8], r):
                combo_series = sample[list(combo)].apply(lambda row: "|".join(str(x) for x in row if pd.notna(x)), axis=1)
                non_null = combo_series[combo_series.str.strip() != ""]
                if len(non_null) == 0:
                    continue
                unique_count = non_null.nunique()
                null_fraction = 1 - (len(non_null) / n)
                unique_fraction = unique_count / len(non_null)
                if unique_fraction >= uniqueness_threshold and null_fraction <= null_threshold:
                    candidates.append(combo)

    return sorted(candidates, key=lambda x: (len(x), x))


def detect_foreign_keys(
    tables: Dict[str, pd.DataFrame],
    pk_candidates: Dict[str, List[Any]],
    fk_threshold: float = 0.8,
    non_null_threshold: float = 0.5,
    sample_size: int = 1000,
) -> List[Dict[str, Any]]:
    """Detect foreign key relationships between tables with fast set intersections."""
    relationships = []
    pk_value_sets: Dict[str, Dict[Any, set]] = {}

    for table_name, pk_list in pk_candidates.items():
        pk_value_sets[table_name] = {}
        df = tables.get(table_name)
        if df is None or df.empty:
            continue

        sample_df = df.head(sample_size)
        for pk in pk_list:
            if isinstance(pk, (tuple, list)) and len(pk) > 1:
                combined = sample_df[list(pk)].apply(lambda row: "|".join(str(x) for x in row if pd.notna(x)), axis=1)
                unique_values = set(combined.dropna().unique())
                pk_value_sets[table_name][tuple(pk)] = unique_values
            else:
                col_name = pk[0] if isinstance(pk, (tuple, list)) else pk
                if col_name in sample_df.columns:
                    unique_values = set(sample_df[col_name].dropna().astype(str).unique())
                    pk_value_sets[table_name][col_name] = unique_values

    for from_table, df in tables.items():
        if df is None or df.empty:
            continue
        sample_from = df.head(sample_size)
        n_rows = len(sample_from)

        for col in sample_from.columns:
            col_series = sample_from[col].dropna().astype(str)
            col_values_set = set(col_series)
            if not col_values_set:
                continue

            non_null_frac = len(col_series) / n_rows
            if non_null_frac < non_null_threshold:
                continue

            for to_table, pk_map in pk_value_sets.items():
                if to_table == from_table:
                    continue

                for pk, valset in pk_map.items():
                    if not valset:
                        continue

                    intersection_size = len(col_values_set.intersection(valset))
                    confidence = intersection_size / len(col_values_set) if col_values_set else 0

                    if confidence >= fk_threshold:
                        unique_fk = col_series.nunique()
                        card = "one-to-one" if unique_fk == len(col_series) else "many-to-one"
                        to_col_str = pk if isinstance(pk, str) else (",".join(str(x) for x in pk) if isinstance(pk, (tuple, list)) else str(pk))

                        relationships.append({
                            "from_table": from_table,
                            "from_column": col,
                            "to_table": to_table,
                            "to_column": to_col_str,
                            "confidence": round(confidence, 3),
                            "non_null_fraction": round(non_null_frac, 3),
                            "cardinality": card,
                        })

    return sorted(relationships, key=lambda x: x["confidence"], reverse=True)



def sanitize_for_yaml(obj: Any) -> Any:
    """Sanitize Python objects for clean, standard YAML serialization without custom tags."""
    if obj is None:
        return None
    if isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, np.ndarray):
        return [sanitize_for_yaml(x) for x in obj.tolist()]
    if isinstance(obj, np.generic):
        py = obj.item()
        if isinstance(py, float) and (math.isnan(py) or math.isinf(py)):
            return None
        return py
    if isinstance(obj, (int, float)):
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        return obj
    if isinstance(obj, Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    if isinstance(obj, pd.Timestamp):
        return None if pd.isna(obj) else obj.isoformat()
    if isinstance(obj, pd.Timedelta):
        return str(obj)
    if isinstance(obj, pd.DataFrame):
        records = obj.to_dict(orient="records")
        return [sanitize_for_yaml(r) for r in records]
    if isinstance(obj, pd.Series):
        return [sanitize_for_yaml(x) for x in obj.dropna().tolist()]
    if isinstance(obj, dict):
        return {str(k): sanitize_for_yaml(v) for k, v in obj.items() if v is not None and has_content(v)}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_yaml(x) for x in obj if x is not None]
    try:
        if hasattr(obj, "tolist"):
            return sanitize_for_yaml(obj.tolist())
    except Exception:
        pass
    try:
        return str(obj)
    except Exception:
        return None


def generate_semantic_model_yaml(
    schemas: List[Dict[str, Any]],
    relationships: Optional[List[Dict[str, Any]]] = None,
    pk_candidates_map: Optional[Dict[str, List[Any]]] = None,
    dataset_name: str = "dataset",
    generated_by: str = "datacon_pipeline",
    include_timestamp: bool = True,
) -> str:
    """Generate a semantic model YAML string combining tables, columns, and relationships."""
    model: Dict[str, Any] = {
        "generated_by": generated_by,
        "dataset": dataset_name,
        "tables": [],
    }

    if include_timestamp:
        model["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    fk_by_table_from: Dict[str, List[Dict[str, Any]]] = {}
    if relationships:
        for r in relationships:
            fk_by_table_from.setdefault(r.get("from_table", ""), []).append(r)

    for s in schemas:
        original_table_name = s.get("table_name")
        if not original_table_name:
            continue

        table_name = original_table_name
        clean_table_name = Path(original_table_name).stem
        rows_sampled = s.get("rows_sampled", None)
        row_count = s.get("row_count", None)

        table_entry: Dict[str, Any] = {
            "table_name": table_name,
            "file_path": s.get("file_path", s.get("source", "")),
            "source": s.get("source", s.get("file_path", "")),
            "row_count": row_count,
            "rows_sampled": rows_sampled,
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
            "columns": [],
            "primary_key": [],
            "foreign_keys": [],
        }

        for col_meta in s.get("columns", []):
            table_entry["columns"].append({
                "name": col_meta.get("name"),
                "type": col_meta.get("type", "VARCHAR"),
                "description": col_meta.get("description", ""),
                "sample_values": col_meta.get("sample_values", []),
            })

        # Add primary keys
        pk_lookup_name = clean_table_name
        if pk_candidates_map and pk_lookup_name in pk_candidates_map:
            pks = pk_candidates_map[pk_lookup_name]
            if has_content(pks):
                pk_listed = []
                for pk in pks:
                    if isinstance(pk, (tuple, list)):
                        pk_listed.extend(list(pk))
                    else:
                        pk_listed.append(pk)
                table_entry["primary_key"] = [str(p) for p in sorted(set(pk_listed)) if p]

        # Add foreign keys
        fks = fk_by_table_from.get(clean_table_name, []) or fk_by_table_from.get(table_name, [])
        for fk in fks:
            table_entry["foreign_keys"].append({
                "from_column": fk.get("from_column"),
                "to_table": fk.get("to_table"),
                "to_column": fk.get("to_column"),
                "confidence": float(fk.get("confidence", 0.0)),
                "non_null_fraction": float(fk.get("non_null_fraction", 0.0)),
                "cardinality": fk.get("cardinality", "many-to-one"),
            })

        model["tables"].append(table_entry)

    sanitized = sanitize_for_yaml(model)
    yaml_text = yaml.safe_dump(sanitized, sort_keys=False, default_flow_style=False, allow_unicode=True)

    # Clean any numpy multiarray scalar tags if present
    yaml_text = re.sub(r"!!python/object/apply:numpy\._core\.multiarray\.scalar\n.*?\n.*?\n", "", yaml_text, flags=re.DOTALL)
    yaml_text = re.sub(r"!!python/object/apply:numpy\.core\.multiarray\.scalar\n.*?\n.*?\n", "", yaml_text, flags=re.DOTALL)
    return yaml_text


def get_data_storage_dir() -> str:
    """Resolve the directory where data source data is stored."""
    db_path = settings.query_engine_db_path
    if db_path:
        directory = os.path.dirname(db_path)
        if directory:
            return directory
    return "./data"


def generate_and_save_semantic_model(
    tables_dict: Dict[str, pd.DataFrame],
    output_dir: Optional[str] = None,
    dataset_name: str = "dataset",
    source_id: Optional[str] = None,
    generated_by: str = "datacon_pipeline",
    relation_sample_size: int = 1000,
) -> Tuple[str, str]:
    """Analyze DataFrames from connectors or data sources, generate semantic model YAML,
    and save it in the data storage directory.

    Args:
        tables_dict: Mapping of table_name -> DataFrame.
        output_dir: Directory where the data is stored (defaults to data storage dir).
        dataset_name: Name of the dataset or connector/source.
        source_id: Optional unique identifier for the connector or document.
        generated_by: Metadata label for provenance.
        relation_sample_size: Max rows sampled for relationship / PK analysis.

    Returns:
        Tuple of (yaml_filename, full_yaml_file_path).
    """
    if not tables_dict:
        logger.warning("[SemanticModel] No tables provided for semantic model generation.")
        return "", ""

    target_dir = output_dir or get_data_storage_dir()
    os.makedirs(target_dir, exist_ok=True)

    logger.info("[SemanticModel] Generating semantic model for %d table(s) in directory '%s'...", len(tables_dict), target_dir)

    schemas = []
    tables_for_fk: Dict[str, pd.DataFrame] = {}
    pk_candidates_map: Dict[str, List[Any]] = {}

    for raw_name, df in tables_dict.items():
        if df is None or not isinstance(df, pd.DataFrame):
            continue

        clean_table_name = Path(raw_name).stem.replace(" ", "_").replace("-", "_").lower()
        tables_for_fk[clean_table_name] = df

        sample = df.head(100)
        rel_sample = df.head(relation_sample_size) if len(df) > relation_sample_size else df

        # Column analysis
        columns = []
        for col in df.columns:
            col_str = str(col)
            sample_vals = _first_nonempty_samples(df[col_str], n=5)
            pandas_type = str(df[col_str].dtype)
            sql_type = infer_column_type_from_samples(sample_vals, df[col_str])
            columns.append({
                "name": col_str,
                "type": sql_type,
                "pandas_type": pandas_type,
                "sample_values": sample_vals,
                "description": f"Column '{col_str}' in {clean_table_name}",
            })

        # Primary key inference
        pks = infer_primary_keys(rel_sample, max_composite=2, uniqueness_threshold=0.98, null_threshold=0.02)
        pk_candidates_map[clean_table_name] = [list(pk) if isinstance(pk, tuple) else [pk] for pk in (pks or [])]

        schemas.append({
            "table_name": clean_table_name,
            "source": raw_name,
            "file_path": raw_name,
            "row_count": len(df),
            "rows_sampled": len(rel_sample),
            "columns": columns,
            "primary_key": pk_candidates_map.get(clean_table_name, []),
        })

    if not schemas:
        logger.warning("[SemanticModel] No valid table schemas created.")
        return "", ""

    # Foreign key detection
    relationships = []
    if len(tables_for_fk) > 1:
        try:
            relationships = detect_foreign_keys(tables_for_fk, pk_candidates_map, fk_threshold=0.8, non_null_threshold=0.5)
            logger.info("[SemanticModel] Detected %d foreign key relationship(s).", len(relationships))
        except Exception as e:
            logger.warning("[SemanticModel] Foreign key detection encountered an error: %s", e)

    first_table = schemas[0]["table_name"] if schemas else dataset_name
    yaml_text = generate_semantic_model_yaml(
        schemas=schemas,
        relationships=relationships or None,
        pk_candidates_map=pk_candidates_map,
        dataset_name=dataset_name or first_table,
        generated_by=generated_by,
        include_timestamp=True,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    id_tag = f"_{source_id}" if source_id else ""
    yaml_filename = f"semantic_model{id_tag}_{timestamp}.yaml"
    full_yaml_path = os.path.join(target_dir, yaml_filename)

    # Save timestamped YAML
    with open(full_yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_text)

    # Also maintain latest semantic_model.yaml and active_schema.yaml in the storage directory
    latest_path = os.path.join(target_dir, "semantic_model.yaml")
    active_path = os.path.join(target_dir, "active_schema.yaml")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(yaml_text)
    with open(active_path, "w", encoding="utf-8") as f:
        f.write(yaml_text)

    logger.info("[SemanticModel] Saved semantic model YAML to '%s' (and updated '%s')", full_yaml_path, latest_path)
    return yaml_filename, full_yaml_path
