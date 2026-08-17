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


def ranking_insight(subject: str, top_label: str, top_value: int | float, top_metric_id: str, total: int | float) -> Insight:
    """A single grounded observation calling out the leading category in a
    ranked breakdown (e.g. tickets grouped by category)."""
    share = percentage(top_value, total)
    return Insight(
        type="neutral",
        text=f"{top_label} has the most {subject} ({top_value}, {share}%).",
        evidence=[top_metric_id],
    )
