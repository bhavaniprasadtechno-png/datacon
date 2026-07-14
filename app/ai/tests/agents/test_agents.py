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
    assert prep.payload == {"columns": [], "rows": []}


@pytest.mark.asyncio
async def test_descriptive_answers_a_free_form_question_grounded_in_real_data():
    snapshot_store.load_dataset("leads", pd.DataFrame({"id": [1, 2, 3]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT COUNT(*) AS total_leads FROM leads")):
        prep = await descriptive.prepare("what are total leads")
    assert prep.payload == {"columns": ["total_leads"], "rows": [[3]]}
    assert "total_leads" in prep.prompt


@pytest.mark.asyncio
async def test_diagnostic_reports_no_data_when_nothing_is_connected():
    prep = await diagnostic.prepare("why did tickets spike?")
    assert "no day-by-day event data" in prep.offline_text.lower()
    assert prep.payload == {"citations": [], "correlation": None}


@pytest.mark.asyncio
async def test_diagnostic_computes_a_real_spike_from_a_free_form_query():
    snapshot_store.load_dataset("tickets", pd.DataFrame({"day": [1, 2], "region": ["EMEA", "EMEA"], "count": [40, 98]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT day, region, count FROM tickets ORDER BY day")), \
         patch.object(diagnostic, "chroma_query", return_value=[]):
        prep = await diagnostic.prepare("why did tickets spike?")
    assert "EMEA" in prep.offline_text
    assert "+145%" in prep.offline_text


@pytest.mark.asyncio
async def test_predictive_reports_no_data_when_nothing_is_connected():
    prep = await predictive.prepare("forecast next quarter")
    assert "no revenue history" in prep.offline_text.lower()
    assert prep.payload == {"series": []}


@pytest.mark.asyncio
async def test_predictive_forecasts_from_a_real_free_form_query():
    snapshot_store.load_dataset("revenue", pd.DataFrame({"month": [1, 2, 3, 4], "revenue": [3.0, 3.1, 3.3, 3.5]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT month, revenue FROM revenue ORDER BY month")):
        prep = await predictive.prepare("forecast next quarter")
    assert prep.payload["series"] == [
        {"label": "p0", "value": 3.0},
        {"label": "p1", "value": 3.1},
        {"label": "p2", "value": 3.3},
        {"label": "p3", "value": 3.5},
    ]
    assert prep.payload["model"] == "Holt-Winters"


@pytest.mark.asyncio
async def test_prescriptive_reports_no_data_when_nothing_is_connected():
    prep = await prescriptive.prepare("how do we reduce churn?")
    assert "no churn data" in prep.offline_text.lower()
    assert prep.payload == {"actions": []}


@pytest.mark.asyncio
async def test_prescriptive_builds_actions_from_a_real_free_form_query():
    snapshot_store.load_dataset("churn", pd.DataFrame({"churn_pct": [3.1], "prev_churn_pct": [3.5], "at_risk_accounts": [12]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT churn_pct, prev_churn_pct, at_risk_accounts FROM churn")):
        prep = await prescriptive.prepare("how do we reduce churn?")
    assert len(prep.payload["actions"]) == 3
    assert "12 at-risk" in prep.payload["actions"][0]["title"]
    assert "3.1" in prep.offline_text
