"""The structured agent response contract — the wire shape a specialized
analyst hands to the frontend. Deterministic facts (metrics) and grounded
insights are validated data, not free text; the LLM only ever supplies the
Summary.text prose, constrained to what's here.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Confidence = Literal["high", "medium", "low"]
MetricFormat = Literal["number", "percentage", "currency", "text"]
InsightType = Literal["positive", "attention", "neutral"]
VisualizationType = Literal[
    "kpi", "line", "area", "bar", "horizontal_bar", "stacked_bar", "grouped_bar",
    "donut", "pie", "funnel", "scatter", "histogram", "heatmap", "table",
    "ranking", "timeline", "map", "none",
]


class _WireModel(BaseModel):
    """Base for every contract model: field names are snake_case in Python,
    serialized as camelCase on the wire (matching the rest of this
    codebase's payload convention — see Citation.documentTitle etc. in
    shared-types/chat.ts). Callers must serialize with `by_alias=True`."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Summary(_WireModel):
    text: str
    confidence: Confidence


class Metric(_WireModel):
    id: str
    label: str
    value: int | float | str
    format: MetricFormat


class Insight(_WireModel):
    type: InsightType
    text: str
    evidence: list[str] = Field(default_factory=list)


class Visualization(_WireModel):
    type: VisualizationType
    title: str | None = None
    data: list[dict[str, Any]] = Field(default_factory=list)


class Table(_WireModel):
    columns: list[str]
    rows: list[list[Any]]
    collapsed: bool = True


class Source(_WireModel):
    dataset: str
    row_count: int


class StructuredResponse(_WireModel):
    summary: Summary
    metrics: list[Metric] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)
    visualizations: list[Visualization] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
