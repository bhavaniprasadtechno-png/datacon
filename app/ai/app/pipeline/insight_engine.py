"""Insight Engine — turns Analytics Engine metrics into grounded,
human-readable insight statements. Every insight carries evidence (metric
IDs) the Validator can check against; nothing here invents a number that
wasn't already computed.
"""
from __future__ import annotations

from app.pipeline.analytics_engine import percentage
from app.pipeline.contracts import Insight


def binary_split_insights(
    subject: str,
    matching_label: str,
    matching_count: int,
    total_count: int,
    rate_metric_id: str,
    matching_metric_id: str,
    total_metric_id: str,
) -> list[Insight]:
    """Given a total split into a matching subset (e.g. active customers)
    and the remainder, produce a positive share insight and, if the
    remainder is non-zero, an attention insight calling it out."""
    if total_count == 0:
        return []

    rate = percentage(matching_count, total_count)
    insights = [
        Insight(
            type="positive",
            text=f"{rate}% of {subject} are {matching_label}.",
            evidence=[rate_metric_id],
        )
    ]

    remainder = total_count - matching_count
    if remainder > 0:
        noun = subject[:-1] if remainder == 1 and subject.endswith("s") else subject
        verb = "is" if remainder == 1 else "are"
        insights.append(
            Insight(
                type="attention",
                text=f"{remainder} {noun} {verb} not {matching_label}.",
                evidence=[total_metric_id, matching_metric_id],
            )
        )

    return insights


def spike_insight(
    subject: str,
    value: float,
    baseline_average: float,
    change_pct: float,
    value_metric_id: str,
    baseline_metric_id: str,
) -> Insight:
    """A direction-agnostic observation calling out a meaningful change
    against a baseline (e.g. a day-by-day count spike). Always the
    "attention" type, whether the change is a rise or a fall — the agent
    producing this has no reliable way to know which direction is
    favorable for an arbitrary connected dataset, unlike a boolean-split
    insight where "positive" is unambiguous."""
    direction = "rose" if change_pct >= 0 else "fell"
    text = f"{subject} {direction} {change_pct:+.1f}% versus the baseline average ({value:.0f} vs {baseline_average:.1f}/day)."
    return Insight(type="attention", text=text, evidence=[value_metric_id, baseline_metric_id])


def ranking_insight(subject: str, top_label: str, top_value: int | float, top_metric_id: str, total: int | float) -> Insight:
    """A single grounded observation calling out the leading category in a
    ranked breakdown (e.g. tickets grouped by category)."""
    share = percentage(top_value, total)
    return Insight(
        type="neutral",
        text=f"{top_label} has the most {subject} ({top_value}, {share}%).",
        evidence=[top_metric_id],
    )
