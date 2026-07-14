import pandas as pd
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.query_engine import snapshot_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers():
    return {"X-Internal-Auth": settings.internal_auth_token}


def test_query_with_no_data_connected_returns_not_ok(client):
    res = client.post("/internal/metrics/query", json={"question": "total revenue"}, headers=_auth_headers())
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["rows"] == []


def test_query_with_data_and_no_llm_configured_still_returns_a_clean_response(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    snapshot_store.load_dataset("orders", pd.DataFrame({"revenue": [10.0]}))
    res = client.post("/internal/metrics/query", json={"question": "total revenue"}, headers=_auth_headers())
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False  # no LLM configured -> generator returns None -> honest non-answer, never a fabricated number
