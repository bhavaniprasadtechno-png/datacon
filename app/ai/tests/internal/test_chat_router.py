import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.query_engine import snapshot_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    monkeypatch.setattr(settings, "gemini_api_key", None)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers():
    return {"X-Internal-Auth": settings.internal_auth_token}


def test_stream_accepts_a_payload_without_a_context_field(client):
    res = client.post("/internal/chat/stream", json={"message": "what are total leads"}, headers=_auth_headers())
    assert res.status_code == 200
    assert "no data is connected" in res.text.lower()


def test_stream_tolerates_a_stray_context_field_for_backward_compatible_rollout(client):
    res = client.post(
        "/internal/chat/stream",
        json={"message": "what are total leads", "context": {"anything": "here"}},
        headers=_auth_headers(),
    )
    assert res.status_code == 200
