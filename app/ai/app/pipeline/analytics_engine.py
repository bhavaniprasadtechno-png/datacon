"""Analytics Engine — deterministic numeric facts computed from a
NormalizedResult. No LLM involvement: totals, counts, percentages, and
grouped aggregations are arithmetic, not language generation.
"""
from __future__ import annotations

from typing import Any, Callable

from app.pipeline.contracts import Metric, MetricFormat
from app.pipeline.normalizer import NormalizedResult


def column_index(result: NormalizedResult, column: str) -> int:
    return [c.name for c in result.columns].index(column)


def total_count(result: NormalizedResult) -> int:
    return result.row_count


def count_where(result: NormalizedResult, column: str, predicate: Callable[[Any], bool]) -> int:
    idx = column_index(result, column)
    return sum(1 for row in result.rows if predicate(row[idx]))


def count_by(result: NormalizedResult, column: str) -> dict[Any, int]:
    idx = column_index(result, column)
    counts: dict[Any, int] = {}
    for row in result.rows:
        counts[row[idx]] = counts.get(row[idx], 0) + 1
    return counts


def percentage(part: float, whole: float) -> float:
    if whole == 0:
        return 0.0
    return round(part / whole * 100, 1)


_FORMAT_BY_VALUE_TYPE: dict[str, MetricFormat] = {"percentage": "percentage", "currency": "currency"}


def rank_categories(result: NormalizedResult, dimension: str, measure: str | None = None) -> list[tuple[Any, int | float]]:
    """Groups rows by `dimension`, aggregating `measure` (summed) if given,
    otherwise counting rows via `count_by`, then ranks the groups descending
    by that value."""
    if measure is None:
        totals: dict[Any, int | float] = count_by(result, dimension)
    else:
        idx = column_index(result, dimension)
        midx = column_index(result, measure)
        totals = {}
        for row in result.rows:
            key = row[idx]
            totals[key] = totals.get(key, 0) + row[midx]
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


def percent_change(value: float, baseline: list[float]) -> float:
    """Percentage change of `value` against the average of a preceding
    baseline set (e.g. today's count vs. the average of prior days)."""
    if not baseline:
        return 0.0
    avg = sum(baseline) / len(baseline)
    if avg == 0:
        return 0.0
    return round((value - avg) / avg * 100, 1)


def primary_metric(result: NormalizedResult, metric_id: str, label: str) -> Metric:
    """The headline number for a result: the query's own aggregate value
    when it already returned exactly one pre-aggregated cell (e.g.
    `SELECT COUNT(*) AS total_leads FROM leads`), otherwise the number of
    entities returned (e.g. `SELECT * FROM customers`)."""
    if result.row_count == 1 and len(result.measures) == 1 and not result.dimensions:
        column = next(c for c in result.columns if c.name == result.measures[0])
        idx = column_index(result, column.name)
        value = result.rows[0][idx]
        fmt = _FORMAT_BY_VALUE_TYPE.get(column.value_type, "number")
        return Metric(id=metric_id, label=label, value=value, format=fmt)
    return Metric(id=metric_id, label=label, value=result.row_count, format="number")
