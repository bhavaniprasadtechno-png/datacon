"""Presentation Planner — decides what the user actually needs to see:
whether a chart is warranted (and never defaults to bar just because rows
came back), and which columns of a table are relevant.
"""
from __future__ import annotations

from typing import Any

from app.pipeline.analytics_engine import rank_categories
from app.pipeline.contracts import Metric, Table, Visualization
from app.pipeline.normalizer import NormalizedResult

_INTERNAL_COLUMN_HINTS = ("internal_id", "embedding", "raw_json", "vector_", "_internal")


def _is_internal_column(name: str) -> bool:
    lname = name.lower()
    return any(hint in lname for hint in _INTERNAL_COLUMN_HINTS)


def _is_category_comparison(result: NormalizedResult) -> bool:
    categorical = [c for c in result.columns if c.value_type == "categorical"]
    return (
        len(categorical) == 1
        and len(result.dimensions) == 1
        and len(result.measures) <= 1
        and result.row_count > 1
    )


def category_ranking(result: NormalizedResult) -> list[tuple[Any, int | float]] | None:
    """Ranked (label, value) pairs for a single-category comparison result
    (e.g. tickets grouped by category) — grouped by its one categorical
    dimension, summing its one measure if present or counting rows if not.
    None when the result isn't shaped like a category comparison."""
    if not _is_category_comparison(result):
        return None
    dimension = result.dimensions[0]
    measure = result.measures[0] if result.measures else None
    return rank_categories(result, dimension, measure)


from app.pipeline.plot_catalog import PLOTS, recommend_plot_from_catalog

_TEMPORAL_COLUMN_HINTS = (
    "date", "time", "month", "year", "quarter", "day", "week",
    "period", "timestamp", "hour", "dt", "created_at", "updated_at", "order_date"
)


def _is_temporal_column(column) -> bool:
    if column.value_type == "date":
        return True
    lname = column.name.lower()
    return any(h in lname for h in _TEMPORAL_COLUMN_HINTS)


def recommend_chart_type(result: NormalizedResult, labels: list[str], question: str = "") -> str:
    """
    Intelligently recommends the best chart visualization type using the PLOTS catalog:
    - 'line': For chronological / temporal trends (dates, months, years, timestamps).
    - 'horizontal_bar': For rankings, top-N comparisons, or categories with long names.
    - 'bar': For vertical discrete comparisons with few items (<= 6) and short labels.
    """
    numeric_cols = [c.name for c in result.columns if c.role == "measure" and not _is_internal_column(c.name)]
    categorical_cols = [c.name for c in result.columns if c.value_type == "categorical" and not _is_internal_column(c.name)]
    date_cols = [c.name for c in result.columns if _is_temporal_column(c) and not _is_internal_column(c.name)]
    columns = [c.name for c in result.columns if not _is_internal_column(c.name)]

    rec = recommend_plot_from_catalog(
        columns=columns,
        row_count=result.row_count,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        date_cols=date_cols,
        sample_labels=labels,
        user_query=question
    )
    return rec.get("ui_chart_type", "horizontal_bar")


def plan_visualization(metrics: list[Metric], result: NormalizedResult, question: str = "") -> Visualization:
    """Selects the most suitable chart visualization for the result.
    - Time-series / temporal trends get a line chart.
    - Category comparisons get a horizontal bar (rankings/long labels) or vertical bar chart.
    - Headline numbers / scalar results get KPI cards."""
    # 1. Check time-series / temporal trend -> Line chart
    date_dims = [c for c in result.columns if _is_temporal_column(c) and not _is_internal_column(c.name)]
    measures = [c for c in result.columns if c.role == "measure" and not _is_internal_column(c.name)]
    if date_dims and measures and result.row_count > 1:
        d_idx = [c.name for c in result.columns].index(date_dims[0].name)
        m_idx = [c.name for c in result.columns].index(measures[0].name)
        data = [
            {"label": str(row[d_idx]), "value": round(float(row[m_idx]), 2)}
            for row in result.rows[:30]
            if row[m_idx] is not None and isinstance(row[m_idx], (int, float))
        ]
        if data:
            return Visualization(type="line", title="CHART", data=data)

    # 2. Check category comparison -> Recommended chart from catalog (horizontal_bar or vertical bar)
    ranked = category_ranking(result)
    if ranked:
        labels = [str(label) for label, _ in ranked[:20]]
        chart_type = recommend_chart_type(result, labels, question=question)
        data = [{"label": str(label), "value": value} for label, value in ranked[:20]]
        return Visualization(type=chart_type, title="CHART", data=data)

    # 3. Headline KPI metrics or none
    if not metrics:
        return Visualization(type="none")
    return Visualization(type="kpi")


def plan_table(result: NormalizedResult, max_rows: int = 20) -> Table:
    """Relevant-column, row-capped, collapsed-by-default table — never the
    full raw dataset with every database column."""
    keep_indexes = [i for i, c in enumerate(result.columns) if not _is_internal_column(c.name)]
    columns = [result.columns[i].name for i in keep_indexes]
    rows = [[row[i] for i in keep_indexes] for row in result.rows[:max_rows]]
    return Table(columns=columns, rows=rows, collapsed=True)
