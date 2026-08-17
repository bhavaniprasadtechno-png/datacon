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


def plan_visualization(metrics: list[Metric], result: NormalizedResult) -> Visualization:
    """Never picks a chart just because rows were returned. A category
    comparison gets a ranked horizontal bar; with headline metrics to show
    otherwise, the KPI cards are the visualization; with neither, there's
    nothing worth visualizing."""
    ranked = category_ranking(result)
    if ranked:
        data = [{"label": str(label), "value": value} for label, value in ranked]
        return Visualization(type="horizontal_bar", data=data)
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
