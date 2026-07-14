import base64

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


def test_csv_ingest_loads_full_rows_into_duckdb(client):
    csv_bytes = b"region,revenue\nNA,10.5\nEMEA,20.0\n"
    payload = {
        "documentId": "doc-abc123",
        "title": "Revenue export",
        "filename": "revenue.csv",
        "contentBase64": base64.b64encode(csv_bytes).decode(),
        "docType": "csv",
    }
    res = client.post("/internal/documents/ingest", json=payload, headers=_auth_headers())

    assert res.status_code == 200
    assert res.json()["rowCount"] == 2

    columns, rows = snapshot_store.execute('SELECT * FROM "csv_doc-abc123" ORDER BY region')
    assert columns == ["region", "revenue"]
    assert rows == [["EMEA", 20.0], ["NA", 10.5]]
