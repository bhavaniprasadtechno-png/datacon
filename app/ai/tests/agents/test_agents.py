from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from app.agents import descriptive, diagnostic, predictive, prescriptive
from app.query_engine import executor, snapshot_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    yield


@pytest.mark.asyncio
async def test_descriptive_reports_no_data_when_nothing_is_connected():
    prep = await descriptive.prepare("what are total leads")
    assert "no data is connected" in prep.offline_text.lower()
    assert prep.payload == {"confidence": "low"}


@pytest.mark.asyncio
async def test_descriptive_answers_a_free_form_question_grounded_in_real_data():
    snapshot_store.load_dataset("leads", pd.DataFrame({"id": [1, 2, 3]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT COUNT(*) AS total_leads FROM leads")):
        prep = await descriptive.prepare("what are total leads")
    assert prep.payload == {
        "confidence": "high",
        "table": {"columns": ["total_leads"], "rows": [[3]]},
    }
    assert "total_leads" in prep.prompt


@pytest.mark.asyncio
async def test_descriptive_adds_a_bar_chart_when_the_result_is_a_small_categorical_comparison():
    snapshot_store.load_dataset("sales", pd.DataFrame({"region": ["EMEA", "APAC"], "revenue": [120.0, 95.0]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT region, revenue FROM sales")):
        prep = await descriptive.prepare("revenue by region")
    assert prep.payload["chart"] == {
        "type": "bar",
        "title": "revenue by region",
        "data": [
            {"label": "EMEA", "value": 120.0},
            {"label": "APAC", "value": 95.0},
        ],
    }


@pytest.mark.asyncio
async def test_descriptive_adds_a_distribution_chart_for_a_low_cardinality_column_in_a_wider_table():
    snapshot_store.load_dataset(
        "leads",
        pd.DataFrame({
            "name": ["Ashwarya Aggarwal", "Deepinder", "Rivisha Tenter", "Jane"],
            "email": ["sherry@x.com", "deep@x.com", "sherry2@x.com", "jane@example.com"],
            "status": ["Won", "Won", "Won", "New"],
        }),
    )
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT name, email, status FROM leads")):
        prep = await descriptive.prepare("give leads")
    assert prep.payload["table"]["columns"] == ["name", "email", "status"]
    assert prep.payload["chart"] == {
        "type": "bar",
        "title": "status distribution",
        "data": [
            {"label": "Won", "value": 3.0},
            {"label": "New", "value": 1.0},
        ],
    }


@pytest.mark.asyncio
async def test_descriptive_prefers_the_lowest_cardinality_column_when_multiple_qualify():
    snapshot_store.load_dataset(
        "leads",
        pd.DataFrame({
            "name": ["Ashwarya Aggarwal", "Deepinder", "Rivisha Tenter", "Jane", "Sam"],
            "company": ["Acme", "Acme", "Beta Corp", "Gamma LLC", "Beta Corp"],
            "status": ["Won", "Won", "Won", "New", "Won"],
        }),
    )
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT name, company, status FROM leads")):
        prep = await descriptive.prepare("give leads")
    assert prep.payload["chart"]["title"] == "status distribution"


@pytest.mark.asyncio
async def test_descriptive_omits_chart_when_no_column_qualifies():
    snapshot_store.load_dataset(
        "leads",
        pd.DataFrame({"name": ["Ashwarya", "Deepinder"], "email": ["a@x.com", "b@x.com"]}),
    )
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT name, email FROM leads")):
        prep = await descriptive.prepare("give leads")
    assert "chart" not in prep.payload


@pytest.mark.asyncio
async def test_descriptive_omits_chart_when_the_grouped_count_query_fails():
    snapshot_store.load_dataset(
        "leads",
        pd.DataFrame({"name": ["A", "B"], "status": ["Won", "New"]}),
    )
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT name, status FROM leads")), \
         patch.object(descriptive, "grouped_count", new=AsyncMock(side_effect=RuntimeError("boom"))):
        prep = await descriptive.prepare("give leads")
    assert prep.payload["table"]["columns"] == ["name", "status"]
    assert "chart" not in prep.payload


@pytest.mark.asyncio
async def test_diagnostic_reports_no_data_when_nothing_is_connected():
    prep = await diagnostic.prepare("why did tickets spike?")
    assert "no day-by-day event data" in prep.offline_text.lower()
    assert prep.payload == {"confidence": "low"}


@pytest.mark.asyncio
async def test_diagnostic_computes_a_real_spike_from_a_free_form_query():
    snapshot_store.load_dataset("tickets", pd.DataFrame({"day": [1, 2], "region": ["EMEA", "EMEA"], "count": [40, 98]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT day, region, count FROM tickets ORDER BY day")), \
         patch.object(diagnostic, "chroma_query", return_value=[]):
        prep = await diagnostic.prepare("why did tickets spike?")
    assert "EMEA" in prep.offline_text
    assert "+145%" in prep.offline_text
    assert prep.payload == {
        "confidence": "medium",
        "table": {"columns": ["region", "count"], "rows": [["EMEA", 40.0], ["EMEA", 98.0]]},
    }


@pytest.mark.asyncio
async def test_diagnostic_marks_high_confidence_with_correlation_when_a_citation_is_found():
    snapshot_store.load_dataset("tickets", pd.DataFrame({"day": [1, 2], "region": ["EMEA", "EMEA"], "count": [40, 98]}))
    hit = {"metadata": {"title": "Incident Report", "filename": "incident.pdf", "chunk_index": 2}, "snippet": "root cause text", "distance": 0.1}
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT day, region, count FROM tickets ORDER BY day")), \
         patch.object(diagnostic, "chroma_query", return_value=[hit]):
        prep = await diagnostic.prepare("why did tickets spike?")
    assert prep.payload["confidence"] == "high"
    assert prep.payload["correlation"] == "spike ↔ Incident Report"
    assert prep.payload["citations"] == [
        {"id": 1, "documentTitle": "Incident Report", "filename": "incident.pdf", "chunkIndex": 2, "snippet": "root cause text"}
    ]


@pytest.mark.asyncio
async def test_predictive_reports_no_data_when_nothing_is_connected():
    prep = await predictive.prepare("forecast next quarter")
    assert "no revenue history" in prep.offline_text.lower()
    assert prep.payload == {"confidence": "low"}


@pytest.mark.asyncio
async def test_predictive_forecasts_from_a_real_free_form_query():
    snapshot_store.load_dataset("revenue", pd.DataFrame({"month": [1, 2, 3, 4], "revenue": [3.0, 3.1, 3.3, 3.5]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT month, revenue FROM revenue ORDER BY month")):
        prep = await predictive.prepare("forecast next quarter")

    chart_data = prep.payload["chart"]["data"]
    assert prep.payload["chart"]["type"] == "line"
    assert prep.payload["chart"]["title"] == "Holt-Winters revenue forecast"
    assert [d["label"] for d in chart_data[:4]] == ["p0", "p1", "p2", "p3"]
    assert [d["value"] for d in chart_data[:4]] == [3.0, 3.1, 3.3, 3.5]
    # Last history point anchors the band's start (lower == upper == its own
    # value) so the shaded region has two adjacent bound-bearing points to
    # span (last actual -> forecast) instead of collapsing to zero width at
    # a single point.
    assert chart_data[3]["lower"] == chart_data[3]["upper"] == 3.5
    forecast_point = chart_data[4]
    assert forecast_point["label"] == "forecast"
    assert forecast_point["lower"] < forecast_point["value"] < forecast_point["upper"]

    assert prep.payload["table"]["columns"] == ["period", "revenue"]
    assert prep.payload["table"]["rows"][:4] == [["p0", 3.0], ["p1", 3.1], ["p2", 3.3], ["p3", 3.5]]
    assert prep.payload["table"]["rows"][4][0] == "forecast"

    assert prep.payload["confidence"] in ("high", "medium", "low")


@pytest.mark.asyncio
async def test_prescriptive_reports_no_data_when_nothing_is_connected():
    prep = await prescriptive.prepare("how do we reduce churn?")
    assert "no churn data" in prep.offline_text.lower()
    assert prep.payload == {"confidence": "low"}


@pytest.mark.asyncio
async def test_prescriptive_builds_actions_from_a_real_free_form_query():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")), \
         patch.object(prescriptive, "chroma_query", return_value=[]):
        prep = await prescriptive.prepare("how do we reduce churn?")
    assert len(prep.payload["actions"]) == 3
    assert "12 at-risk" in prep.payload["actions"][0]["title"]
    assert prep.payload["confidence"] == "high"
    assert "citations" not in prep.payload
    assert "3.1" in prep.offline_text
    for action in prep.payload["actions"]:
        assert action["rationale"]
        assert action["expectedImpact"]
        assert "citationIds" not in action


@pytest.mark.asyncio
async def test_prescriptive_assigns_topic_scoped_citations_per_action():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    billing_hit = {"metadata": {"title": "Billing Postmortem", "filename": "billing.pdf", "chunk_index": 1}, "snippet": "billing errors caused churn", "distance": 0.2}

    def fake_chroma_query(topic, n_results=2):
        if "billing" in topic:
            return [billing_hit]
        return []

    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")), \
         patch.object(prescriptive, "chroma_query", side_effect=fake_chroma_query):
        prep = await prescriptive.prepare("how do we reduce churn?")

    actions = prep.payload["actions"]
    assert "citationIds" not in actions[0]
    assert actions[1]["citationIds"] == [1]
    assert "citationIds" not in actions[2]
    assert prep.payload["citations"] == [
        {"id": 1, "documentTitle": "Billing Postmortem", "filename": "billing.pdf", "chunkIndex": 1, "snippet": "billing errors caused churn"}
    ]


@pytest.mark.asyncio
async def test_prescriptive_deduplicates_a_citation_shared_across_two_actions():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    shared_hit = {"metadata": {"title": "Retention Playbook", "filename": "retention.pdf", "chunk_index": 0}, "snippet": "shared guidance", "distance": 0.15}

    def fake_chroma_query(topic, n_results=2):
        return [shared_hit]

    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")), \
         patch.object(prescriptive, "chroma_query", side_effect=fake_chroma_query):
        prep = await prescriptive.prepare("how do we reduce churn?")

    actions = prep.payload["actions"]
    assert actions[0]["citationIds"] == [1]
    assert actions[1]["citationIds"] == [1]
    assert actions[2]["citationIds"] == [1]
    assert prep.payload["citations"] == [
        {"id": 1, "documentTitle": "Retention Playbook", "filename": "retention.pdf", "chunkIndex": 0, "snippet": "shared guidance"}
    ]
