"""Validator — checks a StructuredResponse's pieces for internal
consistency before it's returned: every insight must cite a real metric,
every table column must exist in the source result. Deterministic, no LLM.
A failing check is scoped to the offending component, not the whole
response, so callers can drop/regenerate just that piece.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.pipeline.contracts import Confidence, Insight, Metric, Table, Visualization
from app.pipeline.normalizer import NormalizedResult

Severity = Literal["blocking", "minor"]

# Types with no chart to draw carry no data — the metrics list is the whole
# visual. A non-empty `data` on one of these means something upstream built
# a chart payload nobody will render.
_DATALESS_VISUALIZATION_TYPES = {"kpi", "none"}


@dataclass
class ValidationIssue:
    severity: Severity
    message: str


def validate(
    metrics: list[Metric],
    insights: list[Insight],
    tables: list[Table],
    result: NormalizedResult,
    visualizations: list[Visualization] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    metric_ids = {m.id for m in metrics}

    for insight in insights:
        if not insight.evidence:
            issues.append(ValidationIssue("blocking", f"insight '{insight.text}' has no evidence"))
            continue
        for ev in insight.evidence:
            if ev not in metric_ids:
                issues.append(
                    ValidationIssue("blocking", f"insight evidence '{ev}' does not reference a known metric")
                )

    source_columns = {c.name for c in result.columns}
    for table in tables:
        for col in table.columns:
            if col not in source_columns:
                issues.append(ValidationIssue("blocking", f"table column '{col}' not in source result"))

    for viz in visualizations or []:
        if viz.type in _DATALESS_VISUALIZATION_TYPES and viz.data:
            issues.append(ValidationIssue("blocking", f"visualization type '{viz.type}' should carry no data"))

    return issues


def compute_confidence(query_ok: bool, issues: list[ValidationIssue]) -> Confidence:
    if not query_ok:
        return "low"
    if any(i.severity == "blocking" for i in issues):
        return "low"
    if any(i.severity == "minor" for i in issues):
        return "medium"
    return "high"
