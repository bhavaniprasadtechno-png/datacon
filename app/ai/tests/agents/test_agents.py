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
    assert payload["visualizations"] == [{"type": "kpi", "title": None, "data": [], "dimension": None, "measure": None}]
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
    assert prep.payload["summary"]["confidence"] == "low"
    assert prep.payload["metrics"] == []
    assert prep.payload["insights"] == []


@pytest.mark.asyncio
async def test_diagnostic_computes_a_real_spike_with_kpi_metrics_a_line_chart_and_a_grounded_insight():
    snapshot_store.load_dataset("tickets", pd.DataFrame({"date": ["2026-08-16", "2026-08-17"], "count": [40, 98]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT date, count FROM tickets ORDER BY date")), \
         patch.object(diagnostic, "chroma_query", return_value=[]):
        prep = await diagnostic.prepare("why did tickets spike?")

    payload = prep.payload
    assert payload["summary"]["confidence"] == "medium"
    assert payload["metrics"] == [
        {"id": "spike_count", "label": "Latest Count", "value": 98.0, "format": "number"},
        {"id": "baseline_avg", "label": "Baseline Average", "value": 40.0, "format": "number"},
        {"id": "percent_change", "label": "Change", "value": 145.0, "format": "percentage"},
    ]
    assert payload["insights"] == [
        {"type": "attention", "text": "Events rose +145.0% versus the baseline average (98 vs 40.0/day).", "evidence": ["spike_count", "baseline_avg"]}
    ]
    for insight in payload["insights"]:
        assert insight["evidence"], "every insight must cite at least one metric"
    assert payload["visualizations"][0]["type"] == "line"
    assert payload["visualizations"][0]["data"] == [
        {"label": "2026-08-16", "value": 40.0},
        {"label": "2026-08-17", "value": 98.0},
    ]
    assert payload["tables"][0]["columns"] == ["date", "count"]
    assert "citations" not in payload
    assert "correlation" not in payload
    assert "+145.0%" in prep.offline_text


@pytest.mark.asyncio
async def test_diagnostic_marks_high_confidence_with_correlation_when_a_citation_is_found():
    snapshot_store.load_dataset("tickets", pd.DataFrame({"date": ["2026-08-16", "2026-08-17"], "count": [40, 98]}))
    hit = {"metadata": {"title": "Incident Report", "filename": "incident.pdf", "chunk_index": 2}, "snippet": "root cause text", "distance": 0.1}
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT date, count FROM tickets ORDER BY date")), \
         patch.object(diagnostic, "chroma_query", return_value=[hit]):
        prep = await diagnostic.prepare("why did tickets spike?")

    payload = prep.payload
    assert payload["summary"]["confidence"] == "high"
    assert payload["correlation"] == "spike ↔ Incident Report"
    assert payload["citations"] == [
        {"id": 1, "documentTitle": "Incident Report", "filename": "incident.pdf", "chunkIndex": 2, "snippet": "root cause text"}
    ]
    assert payload["metrics"][0]["value"] == 98.0
    assert payload["visualizations"][0]["type"] == "line"


@pytest.mark.asyncio
async def test_diagnostic_preserves_citation_metadata_when_falling_back_to_documents():
    hit = {"metadata": {"title": "Runbook", "filename": "runbook.pdf", "chunk_index": 1}, "snippet": "Spikes are usually caused by deploys.", "distance": 0.2}
    with patch.object(diagnostic, "chroma_query", return_value=[hit]):
        prep = await diagnostic.prepare("why did tickets spike?")
    assert prep.payload["citations"] == [
        {"id": 1, "documentTitle": "Runbook", "filename": "runbook.pdf", "chunkIndex": 1, "snippet": "Spikes are usually caused by deploys."}
    ]
    assert prep.payload["confidence"] == "high"


@pytest.mark.asyncio
async def test_predictive_reports_no_data_when_nothing_is_connected():
    prep = await predictive.prepare("forecast next quarter")
    assert "no revenue history" in prep.offline_text.lower()
    assert prep.payload["summary"]["confidence"] == "low"
    assert prep.payload["metrics"] == []


@pytest.mark.asyncio
async def test_predictive_reports_no_data_when_history_is_too_short():
    snapshot_store.load_dataset("revenue", pd.DataFrame({"month": ["2026-01-01"], "revenue": [3.0]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT month, revenue FROM revenue ORDER BY month")):
        prep = await predictive.prepare("forecast next quarter")
    assert "no revenue history" in prep.offline_text.lower()
    assert prep.payload["summary"]["confidence"] == "low"


@pytest.mark.asyncio
async def test_predictive_forecasts_with_kpi_metrics_a_line_chart_and_a_real_confidence_band():
    snapshot_store.load_dataset("revenue", pd.DataFrame({
        "month": ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"],
        "revenue": [3.0, 3.1, 3.3, 3.5],
    }))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT month, revenue FROM revenue ORDER BY month")):
        prep = await predictive.prepare("forecast next quarter")

    payload = prep.payload
    viz = payload["visualizations"][0]
    assert viz["type"] == "line"
    chart_data = viz["data"]
    assert [d["label"] for d in chart_data[:4]] == ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]
    assert [d["value"] for d in chart_data[:4]] == [3.0, 3.1, 3.3, 3.5]
    # Last history point anchors the band's start (lower == upper == its own
    # value) so the shaded region has two adjacent bound-bearing points to
    # span (last actual -> forecast) instead of collapsing to zero width at
    # a single point.
    assert chart_data[3]["lower"] == chart_data[3]["upper"] == 3.5
    forecast_point = chart_data[4]
    assert forecast_point["label"] == "forecast"
    assert forecast_point["lower"] < forecast_point["value"] < forecast_point["upper"]

    metric_ids = [m["id"] for m in payload["metrics"]]
    assert metric_ids == ["projected", "ci_low", "ci_high", "growth_pct"]
    assert payload["metrics"][0]["value"] == forecast_point["value"]
    assert "mape" not in metric_ids

    # Table reflects only the real historical rows — no synthetic forecast row.
    assert payload["tables"][0]["columns"] == ["month", "revenue"]
    assert payload["tables"][0]["rows"] == [
        ["2026-01-01", 3.0], ["2026-02-01", 3.1], ["2026-03-01", 3.3], ["2026-04-01", 3.5],
    ]

    assert payload["summary"]["confidence"] == "high"


@pytest.mark.asyncio
async def test_predictive_lowers_confidence_when_the_model_fit_is_poor():
    snapshot_store.load_dataset("revenue", pd.DataFrame({
        "month": ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"],
        "revenue": [3.0, 8.0, 1.0, 9.0],
    }))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT month, revenue FROM revenue ORDER BY month")):
        prep = await predictive.prepare("forecast next quarter")
    assert prep.payload["summary"]["confidence"] in ("medium", "low")


@pytest.mark.asyncio
async def test_prescriptive_reports_no_data_when_nothing_is_connected():
    prep = await prescriptive.prepare("how do we reduce churn?")
    assert "no churn data" in prep.offline_text.lower()
    assert prep.payload["summary"]["confidence"] == "low"
    assert prep.payload["actions"] == []


@pytest.mark.asyncio
async def test_prescriptive_builds_kpi_metrics_and_actions_from_a_real_free_form_query():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")), \
         patch.object(prescriptive, "chroma_query", return_value=[]):
        prep = await prescriptive.prepare("how do we reduce churn?")

    payload = prep.payload
    metric_ids = [m["id"] for m in payload["metrics"]]
    assert metric_ids == ["churn_pct", "at_risk_accounts", "target_churn_pct"]
    assert payload["metrics"][0]["value"] == 3.1
    assert payload["metrics"][1]["value"] == 12
    # No chart adds value here, but the metrics ARE the visualization — same
    # rule Descriptive uses for a metrics-only, no-chart response.
    assert payload["visualizations"][0]["type"] == "kpi"

    actions = payload["actions"]
    assert len(actions) == 3
    assert "12 at-risk" in actions[0]["title"]
    for action in actions:
        assert action["rationale"]
        assert action["expectedImpact"]
        assert action["citationIds"] == []

    # Every action lacks a supporting citation -> not "high".
    assert payload["summary"]["confidence"] == "medium"
    assert "citations" not in payload
    assert "3.1" in prep.offline_text


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
    assert actions[0]["citationIds"] == []
    assert actions[1]["citationIds"] == [1]
    assert actions[2]["citationIds"] == []
    assert prep.payload["citations"] == [
        {"id": 1, "documentTitle": "Billing Postmortem", "filename": "billing.pdf", "chunkIndex": 1, "snippet": "billing errors caused churn"}
    ]
    # Some, but not all, actions are grounded -> not "high".
    assert prep.payload["summary"]["confidence"] == "medium"


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
    # Every action is grounded -> "high".
    assert prep.payload["summary"]["confidence"] == "high"
