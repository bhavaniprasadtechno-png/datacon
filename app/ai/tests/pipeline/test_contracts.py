import pytest
from pydantic import ValidationError

from app.pipeline.contracts import (
    Action,
    Insight,
    Metric,
    Source,
    StructuredResponse,
    Summary,
    Table,
    Visualization,
)


def test_structured_response_round_trips_through_a_dict():
    response = StructuredResponse(
        summary=Summary(text="You have 4 customers.", confidence="high"),
        metrics=[Metric(id="total_customers", label="Total Customers", value=4, format="number")],
        insights=[Insight(type="positive", text="All customers are active.", evidence=["total_customers"])],
        visualizations=[Visualization(type="none")],
        tables=[Table(columns=["name", "tier"], rows=[["Nimbus Retail", "Enterprise"]], collapsed=True)],
        sources=[Source(dataset="customers", row_count=4)],
    )
    dumped = response.model_dump()
    assert dumped["summary"]["confidence"] == "high"
    assert dumped["metrics"][0]["value"] == 4
    assert dumped["visualizations"][0]["type"] == "none"
    assert dumped["tables"][0]["collapsed"] is True


def test_summary_rejects_an_invalid_confidence_value():
    with pytest.raises(ValidationError):
        Summary(text="x", confidence="extremely-high")


def test_insight_rejects_an_invalid_type_value():
    with pytest.raises(ValidationError):
        Insight(type="sarcastic", text="x", evidence=[])


def test_metric_requires_id_label_value_and_format():
    with pytest.raises(ValidationError):
        Metric(id="total_customers", label="Total Customers")


def test_visualization_defaults_to_no_title_or_data():
    viz = Visualization(type="none")
    assert viz.title is None
    assert viz.data == []
    assert viz.dimension is None
    assert viz.measure is None


def test_visualization_accepts_dimension_and_measure():
    viz = Visualization(type="line", data=[{"label": "2026-08-01", "value": 4}], dimension="day", measure="count")
    assert viz.dimension == "day"
    assert viz.measure == "count"


def test_action_requires_title_rationale_effort_and_owner():
    with pytest.raises(ValidationError):
        Action(title="Launch retention play")


def test_action_rejects_an_invalid_effort_value():
    with pytest.raises(ValidationError):
        Action(title="x", rationale="y", effort="Enormous", owner="Success", expected_impact="z")


def test_action_defaults_to_no_citation_ids():
    action = Action(title="x", rationale="y", effort="Low", owner="Success", expected_impact="z")
    assert action.citation_ids == []


def test_action_serializes_with_camelcase_expected_impact_and_citation_ids():
    action = Action(title="x", rationale="y", effort="Low", owner="Success", expected_impact="z", citation_ids=[1, 2])
    dumped = action.model_dump(by_alias=True)
    assert dumped["expectedImpact"] == "z"
    assert dumped["citationIds"] == [1, 2]
    assert "impact" not in dumped


def test_structured_response_defaults_to_no_actions():
    response = StructuredResponse(summary=Summary(text="x", confidence="low"))
    assert response.actions == []
