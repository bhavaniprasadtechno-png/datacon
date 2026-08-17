from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from app.agents import descriptive, diagnostic, predictive, prescriptive
from app.query_engine import executor, snapshot_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    monkeypatch.setattr(snapshot_store.settings, "database_url", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    yield


@pytest.mark.asyncio
async def test_descriptive_reports_no_data_when_nothing_is_connected():
    prep = await descriptive.prepare("give me customers")
    assert "no data is connected" in prep.offline_text.lower()
    assert prep.payload["summary"]["confidence"] == "low"
    assert prep.payload["metrics"] == []
    assert prep.payload["visualizations"] == []


@pytest.mark.asyncio
async def test_descriptive_answers_customers_with_kpi_metrics_grounded_insights_and_no_forced_chart():
    snapshot_store.load_dataset(
        "customers",
        pd.DataFrame({
            "customer_id": ["CUS-1", "CUS-2", "CUS-3", "CUS-4"],
            "name": ["Nimbus Retail", "Fenwick & Co", "Acme Labs", "Globex"],
            "tier": ["Enterprise", "Growth", "Growth", "Enterprise"],
            "mrr": [4200.0, 1100.0, 800.0, 5000.0],
            "seats": [80, 22, 10, 120],
            "active": [True, True, False, True],
        }),
    )
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT * FROM customers")):
        prep = await descriptive.prepare("give me customers")

    payload = prep.payload
    assert payload["summary"]["confidence"] == "high"
    assert payload["metrics"] == [
        {"id": "total_customers", "label": "Total Customers", "value": 4, "format": "number"},
        {"id": "active_count", "label": "Active Count", "value": 3, "format": "number"},
        {"id": "active_rate", "label": "Active Rate", "value": 75.0, "format": "percentage"},
    ]
    assert {i["type"] for i in payload["insights"]} == {"positive", "attention"}
    assert any(i["text"] == "75.0% of customers are active." for i in payload["insights"])
    assert any(i["text"] == "1 customer is not active." for i in payload["insights"])
    for insight in payload["insights"]:
        assert insight["evidence"], "every insight must cite at least one metric"

    # No forced chart just because rows came back — the KPI cards are the
    # primary visual for this shape (customer_id is dropped upstream by the
    # executor's identifier-column filter, so no internal column leaks either).
    assert payload["visualizations"] == [{"type": "kpi", "title": None, "data": []}]
    assert payload["tables"][0]["columns"] == ["name", "tier", "mrr", "seats", "active"]
    assert payload["tables"][0]["collapsed"] is True
    assert payload["sources"] == [{"dataset": "customers", "rowCount": 4}]
    assert "customer_id" not in prep.prompt  # raw rows never reach the LLM prompt
    assert "75.0" in prep.prompt


@pytest.mark.asyncio
async def test_descriptive_never_forces_a_bar_chart_for_a_category_comparison_result():
    snapshot_store.load_dataset("sales", pd.DataFrame({"region": ["EMEA", "APAC"], "revenue": [120.0, 95.0]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT region, revenue FROM sales")):
        prep = await descriptive.prepare("revenue by region")
    assert prep.payload["visualizations"][0]["type"] == "horizontal_bar"


@pytest.mark.asyncio
async def test_descriptive_answers_a_category_breakdown_with_horizontal_bar_and_ranking_insight():
    snapshot_store.load_dataset(
        "tickets",
        pd.DataFrame({"category": ["Billing", "Bug", "Billing", "Feature", "Bug", "Billing"]}),
    )
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT category FROM tickets")):
        prep = await descriptive.prepare("show tickets by category")

    payload = prep.payload
    assert payload["visualizations"][0]["type"] == "horizontal_bar"
    assert payload["visualizations"][0]["data"] == [
        {"label": "Billing", "value": 3},
        {"label": "Bug", "value": 2},
        {"label": "Feature", "value": 1},
    ]
    assert any(i["text"] == "Billing has the most tickets (3, 50.0%)." for i in payload["insights"])
    for insight in payload["insights"]:
        assert insight["evidence"], "every insight must cite at least one metric"
    assert payload["summary"]["confidence"] == "high"


@pytest.mark.asyncio
async def test_descriptive_reports_insufficient_data_when_the_query_succeeds_with_zero_rows():
    snapshot_store.load_dataset("customers", pd.DataFrame({"tier": ["Enterprise"], "active": [True]}))
    with patch.object(
        executor.generator, "generate_sql",
        new=AsyncMock(return_value="SELECT * FROM customers WHERE tier = 'Nonexistent'"),
    ):
        prep = await descriptive.prepare("give me nonexistent-tier customers")
    assert prep.payload["metrics"] == []
    assert prep.payload["insights"] == []
    assert prep.payload["visualizations"] == []
    assert prep.payload["summary"]["confidence"] == "low"


@pytest.mark.asyncio
async def test_descriptive_strips_the_connector_sync_prefix_from_the_dataset_label():
    snapshot_store.load_dataset("conn_prod-postgres_customers", pd.DataFrame({"name": ["Nimbus", "Fenwick"]}))
    with patch.object(
        executor.generator, "generate_sql",
        new=AsyncMock(return_value='SELECT * FROM "conn_prod-postgres_customers"'),
    ):
        prep = await descriptive.prepare("give me customers")
    assert prep.payload["sources"] == [{"dataset": "customers", "rowCount": 2}]
    assert "conn_" not in prep.offline_text


@pytest.mark.asyncio
async def test_descriptive_preserves_clickable_citation_metadata_when_falling_back_to_documents():
    hit = {
        "metadata": {"title": "Customer Onboarding Guide", "filename": "onboarding.pdf", "chunk_index": 3},
        "snippet": "New customers are provisioned within 24 hours.",
        "distance": 0.1,
    }
    with patch.object(descriptive, "chroma_query", return_value=[hit]):
        prep = await descriptive.prepare("what is our onboarding process")
    assert prep.payload["citations"] == [
        {
            "id": 1,
            "documentTitle": "Customer Onboarding Guide",
            "filename": "onboarding.pdf",
            "chunkIndex": 3,
            "snippet": "New customers are provisioned within 24 hours.",
        }
    ]
    assert prep.payload["confidence"] == "high"


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
