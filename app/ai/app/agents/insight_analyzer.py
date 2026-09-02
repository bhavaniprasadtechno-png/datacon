"""insight_analyzer.py — Programmatic Result Analyzer and Insight Context Builder for DataCon-AI

Provides intelligent, question-aware programmatic compression of full SQL results.
Never truncates raw SQL results blindly (NO arbitrary df.head(10)).
Analyzes 100% of the DataFrame in Python and passes a compact, information-dense
analytical representation to InsightGenerator LLM, drastically reducing token usage
and latency while enhancing analytical accuracy.
"""

import math
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ============================================================================
# UTILITIES & COLUMN DETECTION
# ============================================================================

def _detect_columns(df: pd.DataFrame) -> Tuple[List[str], List[str], List[str]]:
    """Classify DataFrame columns into:
    - temporal_cols: dates, timestamps, years, months, quarters
    - numeric_cols: integers, floats, currencies, counts
    - categorical_cols: strings, categories, IDs, statuses
    """
    temporal_cols = []
    numeric_cols = []
    categorical_cols = []

    temporal_keywords = [
        "date", "time", "year", "month", "quarter", "day", "week",
        "period", "timestamp", "yr", "mo", "dt", "datetime"
    ]

    for col in df.columns:
        col_lower = str(col).lower()
        col_dtype = df[col].dtype

        # Check if already datetime dtype
        if pd.api.types.is_datetime64_any_dtype(col_dtype):
            temporal_cols.append(col)
        # Check if integer year (e.g. 2015-2030) or numeric month (1-12) with temporal name
        elif any(kw in col_lower for kw in temporal_keywords):
            # If string and convertible to date
            if pd.api.types.is_string_dtype(col_dtype) or pd.api.types.is_object_dtype(col_dtype):
                temporal_cols.append(col)
            elif pd.api.types.is_numeric_dtype(col_dtype):
                # If column name explicitly indicates time (e.g. year, month, quarter)
                temporal_cols.append(col)
            else:
                temporal_cols.append(col)
        elif pd.api.types.is_numeric_dtype(col_dtype):
            numeric_cols.append(col)
        else:
            categorical_cols.append(col)

    # If numeric_cols is empty and temporal_cols has numeric-looking columns that aren't purely dates, adjust
    if not numeric_cols:
        for col in list(temporal_cols):
            if pd.api.types.is_numeric_dtype(df[col].dtype) and not any(kw in str(col).lower() for kw in ["year", "quarter", "month", "date"]):
                temporal_cols.remove(col)
                numeric_cols.append(col)

    return temporal_cols, numeric_cols, categorical_cols


def _format_num(val: Any) -> str:
    """Format numeric values cleanly for analytical representation."""
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "N/A"
    if isinstance(val, (int, np.integer)):
        return f"{val:,}"
    if isinstance(val, (float, np.floating)):
        if abs(val) >= 1_000_000:
            return f"{val:,.2f}"
        elif abs(val) >= 1:
            return f"{val:,.2f}"
        elif abs(val) > 0:
            return f"{val:.4f}"
        else:
            return "0.00"
    return str(val)


# ============================================================================
# INTENT DETERMINATION
# ============================================================================

def determine_analytical_intent(
    user_query: str,
    df: pd.DataFrame,
    sql_query: Optional[str] = None
) -> str:
    """Determine the analytical intent of the user question and result structure.
    Categories:
    - time_series / trend
    - ranking
    - comparison
    - anomaly
    - distribution
    - filtering
    - aggregate
    - small_table
    - general
    """
    q = (user_query or "").lower().strip()
    sql = (sql_query or "").lower().strip() if sql_query else ""
    rows, cols = df.shape

    temporal_cols, numeric_cols, categorical_cols = _detect_columns(df)

    # 1. Very small tables (1 row) -> aggregate
    if rows == 1:
        return "aggregate"

    # 2. Anomaly / Spike / Drop / Outlier
    anomaly_keywords = [
        "anomaly", "anomalies", "unusual", "spike", "spikes", "drop", "drops",
        "dip", "outlier", "outliers", "unexpected", "deviation", "deviations",
        "sudden", "abnormal", "why did", "sharp decline", "surge"
    ]
    if any(kw in q for kw in anomaly_keywords):
        return "anomaly"

    # 3. Comparison
    comparison_keywords = [
        "compare", "comparison", " versus ", " vs ", " vs. ", "difference between",
        "higher than", "lower than", "better performing", "relative to", "gap between",
        "which performed better", "compared to", "against"
    ]
    if any(kw in q for kw in comparison_keywords) or (rows in [2, 3, 4] and categorical_cols and numeric_cols):
        return "comparison"

    # 4. Trend / Time-series
    trend_keywords = [
        "trend", "trends", "over time", "monthly", "yearly", "annual", "growth",
        "change over", "history", "by month", "by year", "quarter", "quarterly",
        "5 years", "year over year", "yoy", "mom", "timeline", "trajectory",
        "progression", "evolution", "over the last", "historical", "seasonal",
        "seasonality", "sales trend", "revenue trend"
    ]
    if any(kw in q for kw in trend_keywords) or (temporal_cols and rows >= 4 and numeric_cols):
        # Double check if question is explicitly ranking instead
        if any(kw in q for kw in ["top", "highest", "best", "rank", "bottom", "worst"]) and not any(kw in q for kw in ["trend", "over time", "growth"]):
            return "ranking"
        return "time_series"

    # 5. Ranking
    ranking_keywords = [
        "top", "bottom", "highest", "lowest", "most", "least", "best", "worst",
        "rank", "ranking", "leaders", "leading", "trailing", "largest", "smallest",
        "first", "last", "top performing", "most revenue", "highest sales",
        "highest revenue", "most orders", "top selling"
    ]
    if any(kw in q for kw in ranking_keywords) or ("order by" in sql and ("desc" in sql or "asc" in sql) and categorical_cols and numeric_cols):
        return "ranking"

    # 6. Distribution / Categorical breakdown
    distribution_keywords = [
        "distribution", "breakdown", "share", "percentage of", "proportion",
        "spread", "concentration", "composition", "split", "contribute", "contribution"
    ]
    if any(kw in q for kw in distribution_keywords):
        return "distribution"

    # 7. Filtering / Subset
    filtering_keywords = [
        "delivered", "shipped", "canceled", "filter", "where", "only", "specific",
        "how many", "count of", "status"
    ]
    if any(kw in q for kw in filtering_keywords) and rows <= 10:
        return "filtering"

    # 8. Small general table
    if rows <= 5:
        return "small_table"

    # 9. Categorical analysis fallback if categories and numbers exist
    if categorical_cols and numeric_cols and rows > 5:
        return "ranking"

    # 10. Temporal fallback if temporal columns exist
    if temporal_cols and numeric_cols:
        return "time_series"

    return "general"


# ============================================================================
# PROGRAMMATIC ANALYZERS (OPERATING ON 100% OF DATA)
# ============================================================================

def analyze_time_series(df: pd.DataFrame, user_query: str) -> Dict[str, Any]:
    """Analyze COMPLETE time-series / trend DataFrame (e.g. 60 monthly rows over 5 years).
    Calculates:
    - total periods, start/end values, overall delta and % change
    - multi-year CAGR
    - peaks, troughs (min/max periods and values)
    - period-over-period growth, largest single-period spike and drop
    - multi-year yearly aggregation summary (YoY growth)
    - trajectory direction
    """
    temporal_cols, numeric_cols, _ = _detect_columns(df)

    # Pick primary temporal column and primary metric column
    time_col = temporal_cols[0] if temporal_cols else df.columns[0]
    metric_col = numeric_cols[0] if numeric_cols else (df.columns[1] if len(df.columns) > 1 else df.columns[0])

    # Work on a copy sorted chronologically if possible
    df_sorted = df.copy()
    try:
        df_sorted[time_col] = df_sorted[time_col].astype(str)
        df_sorted = df_sorted.sort_values(by=time_col).reset_index(drop=True)
    except Exception:
        pass

    series_vals = pd.to_numeric(df_sorted[metric_col], errors="coerce").fillna(0.0)
    time_labels = df_sorted[time_col].astype(str).tolist()
    period_count = len(df_sorted)

    if period_count == 0:
        return {"error": "Empty dataset"}

    start_period = time_labels[0]
    end_period = time_labels[-1]
    start_val = float(series_vals.iloc[0])
    end_val = float(series_vals.iloc[-1])

    overall_delta = end_val - start_val
    overall_change_pct = ((end_val - start_val) / start_val * 100.0) if start_val != 0 else None

    # Min and Max
    min_idx = int(series_vals.idxmin())
    max_idx = int(series_vals.idxmax())
    min_period = time_labels[min_idx]
    min_val = float(series_vals.iloc[min_idx])
    max_period = time_labels[max_idx]
    max_val = float(series_vals.iloc[max_idx])

    avg_val = float(series_vals.mean())
    median_val = float(series_vals.median())
    total_val = float(series_vals.sum())

    # Period-over-period changes
    pct_changes = series_vals.pct_change() * 100.0
    valid_changes = pct_changes.dropna()

    largest_increase = None
    largest_decrease = None

    if not valid_changes.empty:
        max_chg_idx = int(valid_changes.idxmax())
        min_chg_idx = int(valid_changes.idxmin())

        largest_increase = {
            "period": time_labels[max_chg_idx],
            "change_pct": round(float(valid_changes.loc[max_chg_idx]), 2),
            "prev_period": time_labels[max_chg_idx - 1],
            "prev_val": _format_num(series_vals.iloc[max_chg_idx - 1]),
            "value": _format_num(series_vals.iloc[max_chg_idx]),
        }

        largest_decrease = {
            "period": time_labels[min_chg_idx],
            "change_pct": round(float(valid_changes.loc[min_chg_idx]), 2),
            "prev_period": time_labels[min_chg_idx - 1],
            "prev_val": _format_num(series_vals.iloc[min_chg_idx - 1]),
            "value": _format_num(series_vals.iloc[min_chg_idx]),
        }

    # Yearly summary aggregation if data spans multiple years (e.g. 2021-01 to 2025-12 or year column)
    yearly_summary = []
    try:
        years = [re.search(r"\b(19\d\d|20\d\d)\b", str(lbl)) for lbl in time_labels]
        if all(y is not None for y in years):
            df_yearly = df_sorted.copy()
            df_yearly["__extracted_year__"] = [y.group(1) for y in years]
            grouped = df_yearly.groupby("__extracted_year__")[metric_col].agg(["sum", "mean", "count"]).reset_index()

            prev_sum = None
            for _, r in grouped.iterrows():
                yr = str(r["__extracted_year__"])
                yr_sum = float(r["sum"])
                yr_avg = float(r["mean"])
                yr_cnt = int(r["count"])
                growth = ((yr_sum - prev_sum) / prev_sum * 100.0) if prev_sum and prev_sum > 0 else None
                yearly_summary.append({
                    "year": yr,
                    "total": _format_num(yr_sum),
                    "average_per_period": _format_num(yr_avg),
                    "periods": yr_cnt,
                    "yoy_growth_pct": round(growth, 1) if growth is not None else None,
                })
                prev_sum = yr_sum
    except Exception:
        yearly_summary = []

    # Calculate CAGR if yearly summary spans > 1 year
    cagr_pct = None
    if len(yearly_summary) >= 2 and start_val > 0 and end_val > 0:
        num_years = len(yearly_summary) - 1
        try:
            cagr = ((end_val / start_val) ** (1.0 / num_years) - 1.0) * 100.0
            cagr_pct = round(cagr, 2)
        except Exception:
            cagr_pct = None

    # Determine overall trajectory
    if overall_change_pct is not None:
        if overall_change_pct > 25:
            trajectory = "Strong upward growth trend"
        elif overall_change_pct > 5:
            trajectory = "Moderate upward trend"
        elif overall_change_pct < -25:
            trajectory = "Significant downward trend"
        elif overall_change_pct < -5:
            trajectory = "Moderate downward trend"
        else:
            trajectory = "Stable / Plateaued"
    else:
        trajectory = "Fluctuating"

    return {
        "analysis_type": "time_series",
        "time_column": str(time_col),
        "metric_column": str(metric_col),
        "period_count": period_count,
        "start_period": start_period,
        "end_period": end_period,
        "start_value": _format_num(start_val),
        "end_value": _format_num(end_val),
        "overall_change_pct": round(overall_change_pct, 2) if overall_change_pct is not None else None,
        "cagr_pct": cagr_pct,
        "trajectory": trajectory,
        "total_metric_sum": _format_num(total_val),
        "average_per_period": _format_num(avg_val),
        "median_per_period": _format_num(median_val),
        "peak_period": {"period": max_period, "value": _format_num(max_val)},
        "trough_period": {"period": min_period, "value": _format_num(min_val)},
        "largest_increase": largest_increase,
        "largest_decrease": largest_decrease,
        "yearly_summary": yearly_summary if len(yearly_summary) > 1 else None,
    }


def analyze_ranking(df: pd.DataFrame, user_query: str) -> Dict[str, Any]:
    """Analyze COMPLETE ranking / category DataFrame (e.g. 74 product categories).
    Calculates:
    - total entity count, total metric sum across 100% of rows
    - average, median, min, max
    - Top 3 to 5 items with value & individual share % of total
    - Top 3 and Top 10 cumulative Pareto concentration %
    - Gap between #1 and #2 (leader margin)
    - Bottom 2 to 3 items
    - Concentration insight (e.g. Pareto distribution)
    """
    temporal_cols, numeric_cols, categorical_cols = _detect_columns(df)

    cat_col = categorical_cols[0] if categorical_cols else df.columns[0]
    metric_col = numeric_cols[0] if numeric_cols else (df.columns[1] if len(df.columns) > 1 else df.columns[0])

    df_clean = df.copy()
    df_clean[metric_col] = pd.to_numeric(df_clean[metric_col], errors="coerce").fillna(0.0)

    # Sort descending by metric
    df_sorted = df_clean.sort_values(by=metric_col, ascending=False).reset_index(drop=True)
    total_entities = len(df_sorted)

    if total_entities == 0:
        return {"error": "Empty dataset"}

    total_sum = float(df_sorted[metric_col].sum())
    avg_val = float(df_sorted[metric_col].mean())
    median_val = float(df_sorted[metric_col].median())
    max_val = float(df_sorted[metric_col].iloc[0])
    min_val = float(df_sorted[metric_col].iloc[-1])

    # Top N items (up to 5)
    top_n_count = min(5, total_entities)
    top_items = []
    for i in range(top_n_count):
        row = df_sorted.iloc[i]
        val = float(row[metric_col])
        share = (val / total_sum * 100.0) if total_sum > 0 else 0.0
        top_items.append({
            "rank": i + 1,
            "entity": str(row[cat_col]),
            "value": _format_num(val),
            "share_pct": round(share, 2),
        })

    # Bottom items (bottom 2-3) if dataset is large (> 5 items)
    bottom_items = []
    if total_entities > 5:
        bot_count = min(3, total_entities - top_n_count)
        for i in range(total_entities - bot_count, total_entities):
            row = df_sorted.iloc[i]
            val = float(row[metric_col])
            share = (val / total_sum * 100.0) if total_sum > 0 else 0.0
            bottom_items.append({
                "rank": i + 1,
                "entity": str(row[cat_col]),
                "value": _format_num(val),
                "share_pct": round(share, 2),
            })

    # Cumulative shares
    top_3_sum = float(df_sorted.iloc[:min(3, total_entities)][metric_col].sum())
    top_3_share = round((top_3_sum / total_sum * 100.0), 2) if total_sum > 0 else 0.0

    top_10_sum = float(df_sorted.iloc[:min(10, total_entities)][metric_col].sum())
    top_10_share = round((top_10_sum / total_sum * 100.0), 2) if total_sum > 0 else 0.0

    # Leader gap
    leader_gap = None
    if total_entities >= 2:
        val_1 = float(df_sorted.iloc[0][metric_col])
        val_2 = float(df_sorted.iloc[1][metric_col])
        gap_abs = val_1 - val_2
        gap_pct = ((val_1 - val_2) / val_2 * 100.0) if val_2 > 0 else None
        leader_gap = {
            "leader": str(df_sorted.iloc[0][cat_col]),
            "runner_up": str(df_sorted.iloc[1][cat_col]),
            "difference": _format_num(gap_abs),
            "lead_margin_pct": round(gap_pct, 1) if gap_pct is not None else None,
        }

    # Concentration insight
    if top_3_share >= 50.0:
        concentration = "Highly concentrated (Top 3 command majority share)"
    elif top_3_share >= 25.0:
        concentration = "Moderately concentrated"
    else:
        concentration = "Well distributed across categories"

    return {
        "analysis_type": "ranking",
        "entity_column": str(cat_col),
        "metric_column": str(metric_col),
        "total_categories_or_items": total_entities,
        "total_metric_sum": _format_num(total_sum),
        "average_per_item": _format_num(avg_val),
        "median_per_item": _format_num(median_val),
        "max_value": _format_num(max_val),
        "min_value": _format_num(min_val),
        "top_items": top_items,
        "top_3_cumulative_share_pct": top_3_share,
        "top_10_cumulative_share_pct": top_10_share if total_entities >= 10 else None,
        "leader_gap": leader_gap,
        "bottom_items": bottom_items if bottom_items else None,
        "concentration_insight": concentration,
    }


def analyze_comparison(df: pd.DataFrame, user_query: str) -> Dict[str, Any]:
    """Analyze comparison datasets (e.g. comparing 2 or a few years, regions, categories).
    Calculates deltas, % difference, ratios, leader/laggard.
    """
    temporal_cols, numeric_cols, categorical_cols = _detect_columns(df)

    entity_col = categorical_cols[0] if categorical_cols else (temporal_cols[0] if temporal_cols else df.columns[0])
    metric_col = numeric_cols[0] if numeric_cols else (df.columns[1] if len(df.columns) > 1 else df.columns[0])

    items = []
    for _, row in df.iterrows():
        try:
            val = float(row[metric_col])
        except Exception:
            val = 0.0
        items.append({
            "entity": str(row[entity_col]),
            "value": val,
            "formatted_value": _format_num(val),
        })

    if not items:
        return {"error": "Empty comparison dataset"}

    comparison_results: Dict[str, Any] = {
        "analysis_type": "comparison",
        "comparison_dimension": str(entity_col),
        "metric_column": str(metric_col),
        "entities_compared": len(items),
        "items": items,
    }

    # If exactly 2 entities, compute head-to-head comparison
    if len(items) == 2:
        item_a = items[0]
        item_b = items[1]
        val_a = item_a["value"]
        val_b = item_b["value"]

        diff = val_b - val_a
        pct_diff = ((val_b - val_a) / val_a * 100.0) if val_a != 0 else None
        ratio = (val_b / val_a) if val_a != 0 else None

        winner = item_b["entity"] if val_b > val_a else (item_a["entity"] if val_a > val_b else "Tied")

        comparison_results["head_to_head"] = {
            "entity_1": item_a["entity"],
            "value_1": item_a["formatted_value"],
            "entity_2": item_b["entity"],
            "value_2": item_b["formatted_value"],
            "absolute_difference": _format_num(abs(diff)),
            "percentage_change": round(pct_diff, 2) if pct_diff is not None else None,
            "ratio": round(ratio, 2) if ratio is not None else None,
            "higher_performer": winner,
        }
    else:
        # Multi-entity comparison
        vals = [it["value"] for it in items]
        max_val = max(vals)
        min_val = min(vals)
        top_ent = next(it["entity"] for it in items if it["value"] == max_val)
        bot_ent = next(it["entity"] for it in items if it["value"] == min_val)
        spread_pct = ((max_val - min_val) / min_val * 100.0) if min_val != 0 else None

        comparison_results["multi_comparison_summary"] = {
            "highest_performer": {"entity": top_ent, "value": _format_num(max_val)},
            "lowest_performer": {"entity": bot_ent, "value": _format_num(min_val)},
            "spread_percentage": round(spread_pct, 2) if spread_pct is not None else None,
        }

    return comparison_results


def analyze_anomaly(df: pd.DataFrame, user_query: str) -> Dict[str, Any]:
    """Analyze ALL rows for statistical anomalies, spikes, drops, and outliers.
    Uses Z-scores (|Z| >= 1.8), IQR thresholds, and sudden period-over-period percentage jumps/drops.
    """
    temporal_cols, numeric_cols, categorical_cols = _detect_columns(df)

    label_col = temporal_cols[0] if temporal_cols else (categorical_cols[0] if categorical_cols else df.columns[0])
    metric_col = numeric_cols[0] if numeric_cols else (df.columns[1] if len(df.columns) > 1 else df.columns[0])

    df_clean = df.copy()
    series_vals = pd.to_numeric(df_clean[metric_col], errors="coerce").fillna(0.0)
    labels = df_clean[label_col].astype(str).tolist()

    if len(series_vals) == 0:
        return {"error": "Empty dataset"}

    mean_val = float(series_vals.mean())
    std_val = float(series_vals.std()) if len(series_vals) > 1 else 0.0
    median_val = float(series_vals.median())

    q25 = float(series_vals.quantile(0.25))
    q75 = float(series_vals.quantile(0.75))
    iqr = q75 - q25

    detected_anomalies = []

    # 1. Statistical Z-score & IQR Outliers
    for idx, (lbl, val) in enumerate(zip(labels, series_vals)):
        z_score = ((val - mean_val) / std_val) if std_val > 0 else 0.0
        is_iqr_outlier = (val > q75 + 1.5 * iqr) or (val < q25 - 1.5 * iqr)

        if abs(z_score) >= 1.8 or is_iqr_outlier:
            dev_from_mean_pct = ((val - mean_val) / mean_val * 100.0) if mean_val != 0 else 0.0
            anomaly_type = "Spike / High Outlier" if val > mean_val else "Drop / Low Outlier"

            # Context (previous and next row)
            prev_row = f"{labels[idx-1]}: {_format_num(series_vals.iloc[idx-1])}" if idx > 0 else None
            next_row = f"{labels[idx+1]}: {_format_num(series_vals.iloc[idx+1])}" if idx < len(labels) - 1 else None

            detected_anomalies.append({
                "period_or_entity": str(lbl),
                "actual_value": _format_num(val),
                "anomaly_type": anomaly_type,
                "z_score": round(z_score, 2),
                "deviation_from_mean_pct": round(dev_from_mean_pct, 1),
                "baseline_mean": _format_num(mean_val),
                "surrounding_context": {"previous": prev_row, "next": next_row},
            })

    # 2. Sudden Period-over-Period Swings (> 40% jump/drop)
    pct_changes = series_vals.pct_change() * 100.0
    for idx in range(1, len(pct_changes)):
        chg = pct_changes.iloc[idx]
        if abs(chg) >= 40.0 and not any(a["period_or_entity"] == str(labels[idx]) for a in detected_anomalies):
            detected_anomalies.append({
                "period_or_entity": str(labels[idx]),
                "actual_value": _format_num(series_vals.iloc[idx]),
                "anomaly_type": "Sharp Period-over-Period Surge" if chg > 0 else "Sharp Period-over-Period Drop",
                "period_change_pct": round(float(chg), 1),
                "previous_period_value": _format_num(series_vals.iloc[idx - 1]),
                "baseline_mean": _format_num(mean_val),
            })

    return {
        "analysis_type": "anomaly",
        "total_records_analyzed": len(df),
        "baseline_statistics": {
            "mean": _format_num(mean_val),
            "median": _format_num(median_val),
            "standard_deviation": _format_num(std_val),
            "normal_range": f"{_format_num(max(0, mean_val - 1.5 * std_val))} to {_format_num(mean_val + 1.5 * std_val)}",
        },
        "anomalies_detected_count": len(detected_anomalies),
        "detected_anomalies": detected_anomalies if detected_anomalies else "No severe statistical anomalies found (data conforms to expected baseline).",
    }


def analyze_aggregate(df: pd.DataFrame, user_query: str) -> Dict[str, Any]:
    """Analyze simple aggregate results (1 row or summary metrics).
    Formats numbers with exact values and minimal overhead.
    """
    rows, cols = df.shape
    if rows == 1:
        metrics = {}
        for col in df.columns:
            val = df.iloc[0][col]
            metrics[str(col)] = _format_num(val) if isinstance(val, (int, float, np.number)) else str(val)
        return {
            "analysis_type": "aggregate",
            "result_type": "single_scalar_summary",
            "metrics": metrics,
        }

    # Multi-row aggregate summary
    temporal_cols, numeric_cols, categorical_cols = _detect_columns(df)
    summary_stats = {}
    for col in numeric_cols:
        col_vals = pd.to_numeric(df[col], errors="coerce").dropna()
        if not col_vals.empty:
            summary_stats[str(col)] = {
                "total_sum": _format_num(col_vals.sum()),
                "average": _format_num(col_vals.mean()),
                "median": _format_num(col_vals.median()),
                "min": _format_num(col_vals.min()),
                "max": _format_num(col_vals.max()),
            }

    cat_stats = {}
    for col in categorical_cols:
        unique_cnt = df[col].nunique()
        top_val = df[col].mode().iloc[0] if not df[col].empty else "N/A"
        cat_stats[str(col)] = {
            "unique_count": unique_cnt,
            "most_frequent": str(top_val),
        }

    return {
        "analysis_type": "aggregate",
        "total_rows": rows,
        "numeric_statistics": summary_stats,
        "categorical_overview": cat_stats,
    }


def analyze_distribution(df: pd.DataFrame, user_query: str) -> Dict[str, Any]:
    """Analyze distribution, spread, percentiles, and concentration."""
    ranking_data = analyze_ranking(df, user_query)
    ranking_data["analysis_type"] = "distribution"
    return ranking_data


def analyze_filtering(df: pd.DataFrame, user_query: str) -> Dict[str, Any]:
    """Analyze filtered query results (e.g. delivered orders, specific country/city)."""
    rows, cols = df.shape
    temporal_cols, numeric_cols, categorical_cols = _detect_columns(df)

    metrics = {}
    for col in numeric_cols:
        col_vals = pd.to_numeric(df[col], errors="coerce").dropna()
        if not col_vals.empty:
            metrics[str(col)] = {
                "sum": _format_num(col_vals.sum()),
                "average": _format_num(col_vals.mean()),
                "max": _format_num(col_vals.max()),
            }

    sample_values = {}
    for col in categorical_cols:
        unique_vals = [str(x) for x in df[col].dropna().unique()[:5]]
        sample_values[str(col)] = unique_vals

    return {
        "analysis_type": "filtering",
        "matched_rows_count": rows,
        "numeric_metrics": metrics,
        "filter_values": sample_values,
    }


def analyze_small_table(df: pd.DataFrame, user_query: str) -> Dict[str, Any]:
    """Handle small results (1-5 rows) cleanly and completely without any loss."""
    records = []
    for _, row in df.iterrows():
        rec = {}
        for col in df.columns:
            val = row[col]
            rec[str(col)] = _format_num(val) if isinstance(val, (int, float, np.number)) else str(val)
        records.append(rec)

    return {
        "analysis_type": "small_table",
        "row_count": len(df),
        "complete_data": records,
    }


# ============================================================================
# INTELLIGENT REPRESENTATIVE ROW SELECTION (NOT BLIND TRUNCATION)
# ============================================================================

def select_important_rows(
    df: pd.DataFrame,
    intent: str,
    analysis_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Select representative milestone rows based on analytical context.
    NEVER uses arbitrary df.head(10).
    - For time-series: start row, end row, peak row, trough row, biggest jump/drop.
    - For ranking: top 3 rows, bottom 2 rows.
    - For comparison: all comparison rows.
    - For anomaly: anomaly rows + their immediate neighbors.
    - For small tables: all rows.
    """
    rows = len(df)
    if rows <= 6:
        return [_clean_row_dict(df.iloc[i]) for i in range(rows)]

    selected_indices = set()

    if intent == "time_series":
        # First and last
        selected_indices.add(0)
        selected_indices.add(rows - 1)

        # Peak and trough if numeric cols exist
        _, numeric_cols, _ = _detect_columns(df)
        if numeric_cols:
            num_s = pd.to_numeric(df[numeric_cols[0]], errors="coerce").fillna(0.0)
            selected_indices.add(int(num_s.idxmax()))
            selected_indices.add(int(num_s.idxmin()))

    elif intent in ["ranking", "distribution"]:
        # Top 3
        for i in range(min(3, rows)):
            selected_indices.add(i)
        # Bottom 2
        for i in range(max(0, rows - 2), rows):
            selected_indices.add(i)

    elif intent == "comparison":
        for i in range(min(10, rows)):
            selected_indices.add(i)

    elif intent == "anomaly":
        # Include top deviations
        _, numeric_cols, _ = _detect_columns(df)
        if numeric_cols:
            num_s = pd.to_numeric(df[numeric_cols[0]], errors="coerce").fillna(0.0)
            selected_indices.add(int(num_s.idxmax()))
            selected_indices.add(int(num_s.idxmin()))
        # Add first and last
        selected_indices.add(0)
        selected_indices.add(rows - 1)

    else:
        # General: first 3 and last 2 with labels
        for i in range(min(3, rows)):
            selected_indices.add(i)
        for i in range(max(0, rows - 2), rows):
            selected_indices.add(i)

    sorted_indices = sorted(list(selected_indices))
    return [_clean_row_dict(df.iloc[i], row_idx=i) for i in sorted_indices]


def _clean_row_dict(row: pd.Series, row_idx: Optional[int] = None) -> Dict[str, Any]:
    """Clean row to serializable dict with formatted numbers."""
    d = {}
    if row_idx is not None:
        d["_row_index"] = row_idx + 1
    for k, v in row.items():
        if isinstance(v, (int, float, np.number)):
            d[str(k)] = _format_num(v)
        else:
            d[str(k)] = str(v)
    return d


# ============================================================================
# CONTEXT BUILDER & TOKEN BUDGET
# ============================================================================

def format_compact_analytical_context(
    analysis_data: Dict[str, Any],
    intent: str,
    df: pd.DataFrame,
    important_rows: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Format analytical findings into high-density, concise text to minimize input tokens."""
    rows, cols = df.shape
    lines = []

    if intent == "time_series":
        lines.append(f"Analysis Type: Time Series Trend ({rows} periods analyzed)")
        lines.append(f"Period Range: {analysis_data.get('start_period')} to {analysis_data.get('end_period')}")
        cagr_str = f" | CAGR: {analysis_data.get('cagr_pct')}%" if analysis_data.get("cagr_pct") is not None else ""
        lines.append(
            f"Trajectory: {analysis_data.get('trajectory')} | "
            f"Start: {analysis_data.get('start_value')} | "
            f"End: {analysis_data.get('end_value')} | "
            f"Overall Change: {analysis_data.get('overall_change_pct')}%"
            + cagr_str
        )
        lines.append(
            f"Aggregates: Total Sum={analysis_data.get('total_metric_sum')} | "
            f"Period Avg={analysis_data.get('average_per_period')} | "
            f"Median={analysis_data.get('median_per_period')}"
        )
        peak = analysis_data.get("peak_period", {})
        trough = analysis_data.get("trough_period", {})
        lines.append(f"Peak: {peak.get('period')} ({peak.get('value')}) | Trough: {trough.get('period')} ({trough.get('value')})")

        inc = analysis_data.get("largest_increase")
        dec = analysis_data.get("largest_decrease")
        if inc:
            lines.append(f"Max Period Increase: {inc.get('period')} (+{inc.get('change_pct')}%, from {inc.get('prev_val')} to {inc.get('value')})")
        if dec:
            lines.append(f"Max Period Decrease: {dec.get('period')} ({dec.get('change_pct')}%, from {dec.get('prev_val')} to {dec.get('value')})")

        yearly = analysis_data.get("yearly_summary")
        if yearly:
            lines.append("Yearly Aggregations:")
            for yr in yearly:
                growth_str = f" ({yr['yoy_growth_pct']}% YoY)" if yr.get("yoy_growth_pct") is not None else ""
                lines.append(f"  - {yr['year']}: Total={yr['total']}, Avg={yr['average_per_period']}{growth_str}")

    elif intent in ["ranking", "distribution"]:
        lines.append(f"Analysis Type: Ranking & Distribution ({analysis_data.get('total_categories_or_items')} entities analyzed across 100% of data)")
        lines.append(
            f"Summary: Total Metric Sum={analysis_data.get('total_metric_sum')} | "
            f"Mean per Entity={analysis_data.get('average_per_item')} | "
            f"Median={analysis_data.get('median_per_item')}"
        )
        top10_str = f", Top 10 Share: {analysis_data.get('top_10_cumulative_share_pct')}%" if analysis_data.get("top_10_cumulative_share_pct") else ""
        lines.append(
            f"Concentration: {analysis_data.get('concentration_insight')} "
            f"(Top 3 Share: {analysis_data.get('top_3_cumulative_share_pct')}%"
            + top10_str
            + ")"
        )
        gap = analysis_data.get("leader_gap")
        if gap:
            lines.append(f"Leader Gap: #{gap['leader']} leads #{gap['runner_up']} by {gap['difference']} (+{gap['lead_margin_pct']}%)")

        top_items = analysis_data.get("top_items", [])
        if top_items:
            lines.append("Top Performers:")
            for it in top_items:
                lines.append(f"  #{it['rank']} {it['entity']}: {it['value']} ({it['share_pct']}% share)")

        bottom_items = analysis_data.get("bottom_items", [])
        if bottom_items:
            lines.append("Bottom Performers:")
            for it in bottom_items:
                lines.append(f"  #{it['rank']} {it['entity']}: {it['value']} ({it['share_pct']}% share)")

    elif intent == "comparison":
        lines.append(f"Analysis Type: Comparison ({analysis_data.get('entities_compared')} entities)")
        h2h = analysis_data.get("head_to_head")
        if h2h:
            lines.append(f"Entity 1 ({h2h['entity_1']}): {h2h['value_1']}")
            lines.append(f"Entity 2 ({h2h['entity_2']}): {h2h['value_2']}")
            lines.append(f"Absolute Difference: {h2h['absolute_difference']}")
            if h2h.get("percentage_change") is not None:
                lines.append(f"Growth / Change: {h2h['percentage_change']}% ({h2h.get('ratio')}x multiplier)")
            lines.append(f"Top Performer: {h2h['higher_performer']}")
        else:
            items = analysis_data.get("items", [])
            for it in items:
                lines.append(f"  - {it['entity']}: {it['formatted_value']}")
            summ = analysis_data.get("multi_comparison_summary", {})
            if summ:
                lines.append(f"Highest: {summ.get('highest_performer', {}).get('entity')} ({summ.get('highest_performer', {}).get('value')})")
                lines.append(f"Lowest: {summ.get('lowest_performer', {}).get('entity')} ({summ.get('lowest_performer', {}).get('value')})")
                lines.append(f"Spread: {summ.get('spread_percentage')}%")

    elif intent == "anomaly":
        lines.append(f"Analysis Type: Anomaly & Outlier Detection ({analysis_data.get('total_records_analyzed')} records evaluated)")
        b = analysis_data.get("baseline_statistics", {})
        lines.append(f"Statistical Baseline: Mean={b.get('mean')}, Median={b.get('median')}, StdDev={b.get('standard_deviation')}, Expected Normal Range={b.get('normal_range')}")
        anomalies = analysis_data.get("detected_anomalies", [])
        if isinstance(anomalies, list) and anomalies:
            lines.append(f"Detected Anomalies ({len(anomalies)} found):")
            for a in anomalies:
                dev = f" (Dev: {a.get('deviation_from_mean_pct')}%, Z={a.get('z_score')})" if "z_score" in a else f" (Change: {a.get('period_change_pct')}%)"
                lines.append(f"  - {a.get('period_or_entity')}: {a.get('actual_value')} [{a.get('anomaly_type')}]{dev}")
        else:
            lines.append(f"Detected Anomalies: {anomalies}")

    elif intent == "aggregate":
        lines.append(f"Analysis Type: Aggregate Summary ({rows} row(s))")
        if "metrics" in analysis_data:
            for k, v in analysis_data["metrics"].items():
                lines.append(f"  - {k}: {v}")
        if "numeric_statistics" in analysis_data:
            for col, stats in analysis_data["numeric_statistics"].items():
                lines.append(f"  - {col}: Sum={stats['total_sum']}, Avg={stats['average']}, Min={stats['min']}, Max={stats['max']}")

    elif intent == "filtering":
        lines.append(f"Analysis Type: Filtered Query Result ({analysis_data.get('matched_rows_count')} matching rows)")
        for col, metrics in analysis_data.get("numeric_metrics", {}).items():
            lines.append(f"  - {col}: Sum={metrics['sum']}, Avg={metrics['average']}, Max={metrics['max']}")
        for col, vals in analysis_data.get("filter_values", {}).items():
            lines.append(f"  - {col} values: {', '.join(vals)}")

    else:
        # Small table / general
        lines.append(f"Analysis Type: Result Overview ({rows} rows, {cols} columns)")
        records = analysis_data.get("complete_data", [])
        if records:
            for r in records[:5]:
                r_str = ", ".join([f"{k}={v}" for k, v in r.items()])
                lines.append(f"  - {r_str}")

    return "\n".join(lines)


def build_insight_context(
    df: pd.DataFrame,
    user_query: str,
    sql_query: Optional[str] = None
) -> Dict[str, Any]:
    """Master function: Analyze 100% of the DataFrame programmatically and build a compact,
    structured analytical context for InsightGenerator LLM.
    """
    if df is None or df.empty:
        return {
            "intent": "empty",
            "original_rows": 0,
            "original_columns": 0,
            "formatted_context": "The query returned 0 rows (no matching data).",
            "max_tokens": 150,
        }

    rows, cols = df.shape
    intent = determine_analytical_intent(user_query, df, sql_query)

    # Dispatch to specific analytical calculator
    if intent == "time_series":
        analysis_data = analyze_time_series(df, user_query)
    elif intent == "ranking":
        analysis_data = analyze_ranking(df, user_query)
    elif intent == "comparison":
        analysis_data = analyze_comparison(df, user_query)
    elif intent == "anomaly":
        analysis_data = analyze_anomaly(df, user_query)
    elif intent == "distribution":
        analysis_data = analyze_distribution(df, user_query)
    elif intent == "filtering":
        analysis_data = analyze_filtering(df, user_query)
    elif intent == "small_table":
        analysis_data = analyze_small_table(df, user_query)
    else:
        analysis_data = analyze_aggregate(df, user_query)

    # Select representative milestone rows
    important_rows = select_important_rows(df, intent, analysis_data)

    # High-density compact formatted context
    formatted_context = format_compact_analytical_context(
        analysis_data=analysis_data,
        intent=intent,
        df=df,
        important_rows=important_rows
    )

    # Target output token budget based on analytical complexity
    max_tokens = get_output_token_budget(intent)

    return {
        "intent": intent,
        "original_rows": rows,
        "original_columns": cols,
        "analysis_data": analysis_data,
        "important_rows": important_rows,
        "formatted_context": formatted_context,
        "context_size_chars": len(formatted_context),
        "max_tokens": max_tokens,
    }


def get_output_token_budget(intent: str) -> int:
    """Get recommended LLM max_tokens for generation based on analytical complexity.
    Prevents verbose runaway essays while providing enough room for complete insights.
    """
    budgets = {
        "aggregate": 220,
        "small_table": 250,
        "filtering": 300,
        "comparison": 380,
        "ranking": 420,
        "time_series": 550,
        "anomaly": 480,
        "distribution": 450,
        "general": 400,
    }
    return budgets.get(intent, 400)
