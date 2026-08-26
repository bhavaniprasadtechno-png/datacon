import os
import base64
import yaml
import pandas as pd
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.query_engine import snapshot_store, semantic_model
from app.connectors import service as connectors_service
from app.connectors.types import DatasetResult, SyncResult


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    monkeypatch.setattr(snapshot_store.settings, "database_url", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers():
    return {"X-Internal-Auth": settings.internal_auth_token}


def test_infer_primary_keys_single_and_composite():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "category": ["A", "A", "B", "B", "C"],
        "sub_id": [10, 20, 10, 20, 10],
        "val": [100, 100, 100, 100, 100],
    })
    pks = semantic_model.infer_primary_keys(df)
    assert ("id",) in pks
    assert ("category", "sub_id") in pks or ("sub_id", "category") in pks


def test_infer_column_type_from_samples():
    s_int = pd.Series([1, 2, 3, 4])
    assert semantic_model.infer_column_type_from_samples(["1", "2", "3"], s_int) == "INTEGER"

    s_float = pd.Series([1.5, 2.5, 3.0])
    assert semantic_model.infer_column_type_from_samples(["1.5", "2.5"], s_float) == "FLOAT"

    s_bool = pd.Series([True, False, True])
    assert semantic_model.infer_column_type_from_samples(["True", "False"], s_bool) == "BOOLEAN"

    s_date = pd.Series(["2024-01-01", "2024-02-01", "2024-03-01"])
    assert semantic_model.infer_column_type_from_samples(["2024-01-01", "2024-02-01"], s_date) == "TIMESTAMP"


def test_detect_foreign_keys():
    users_df = pd.DataFrame({
        "user_id": ["u1", "u2", "u3"],
        "name": ["Alice", "Bob", "Charlie"],
    })
    orders_df = pd.DataFrame({
        "order_id": [101, 102, 103, 104],
        "user_id": ["u1", "u2", "u1", "u3"],
        "amount": [50.0, 75.0, 20.0, 100.0],
    })
    tables = {"users": users_df, "orders": orders_df}
    pk_map = {"users": [("user_id",)], "orders": [("order_id",)]}

    fks = semantic_model.detect_foreign_keys(tables, pk_map)
    assert len(fks) >= 1
    match = next((fk for fk in fks if fk["from_table"] == "orders" and fk["to_table"] == "users"), None)
    assert match is not None
    assert match["from_column"] == "user_id"
    assert match["to_column"] == "user_id"
    assert match["confidence"] == 1.0


def test_generate_and_save_semantic_model(tmp_path):
    df_customers = pd.DataFrame({
        "customer_id": [1, 2, 3],
        "email": ["a@test.com", "b@test.com", "c@test.com"],
        "active": [True, True, False],
    })
    df_orders = pd.DataFrame({
        "order_id": [10, 20, 30],
        "customer_id": [1, 2, 1],
        "total": [19.99, 45.50, 10.00],
    })
    tables = {"customers": df_customers, "orders": df_orders}

    yaml_name, yaml_path = semantic_model.generate_and_save_semantic_model(
        tables_dict=tables,
        output_dir=str(tmp_path),
        dataset_name="ecommerce",
        source_id="test_src",
    )

    assert os.path.exists(yaml_path)
    assert os.path.exists(tmp_path / "semantic_model.yaml")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["dataset"] == "ecommerce"
    assert len(data["tables"]) == 2
    table_names = [t["table_name"] for t in data["tables"]]
    assert "customers" in table_names
    assert "orders" in table_names


def test_sync_connector_generates_yaml(tmp_path):
    fake_sync = SyncResult(
        True,
        "Discovered 2 tables.",
        [
            DatasetResult(name="users", columns=["id", "name"], row_count=2, sample_rows=[["1", "Alice"]], rows=[(1, "Alice"), (2, "Bob")]),
            DatasetResult(name="orders", columns=["order_id", "user_id"], row_count=2, sample_rows=[["10", "1"]], rows=[(10, 1), (20, 2)]),
        ],
    )
    with patch.object(connectors_service.sqlite_driver, "sync", return_value=fake_sync):
        connectors_service.sync_connector("sqlite", {"database": "testdb"}, {}, connector_id="conn_abc")

    # Check that YAML file was generated in the data directory
    data_dir = tmp_path
    yaml_files = list(data_dir.glob("*.yaml"))
    assert len(yaml_files) >= 1

    latest_yaml = data_dir / "semantic_model.yaml"
    assert latest_yaml.exists()
    with open(latest_yaml, "r", encoding="utf-8") as f:
        content = yaml.safe_load(f)
    assert len(content["tables"]) == 2


def test_csv_and_xlsx_ingest_generates_yaml(client, tmp_path):
    # 1. Ingest CSV
    csv_bytes = b"product_id,price,in_stock\nP1,19.99,True\nP2,29.99,False\n"
    payload = {
        "documentId": "doc-csv1",
        "title": "Products Catalog",
        "filename": "products.csv",
        "contentBase64": base64.b64encode(csv_bytes).decode(),
        "docType": "csv",
    }
    res = client.post("/internal/documents/ingest", json=payload, headers=_auth_headers())
    assert res.status_code == 200

    latest_yaml = tmp_path / "semantic_model.yaml"
    assert latest_yaml.exists()
    with open(latest_yaml, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert len(data["tables"]) == 1
    assert data["tables"][0]["table_name"] == "csv_doc_csv1"

    # 2. Ingest XLSX
    import io
    xlsx_buf = io.BytesIO()
    excel_df = pd.DataFrame({"sku": ["SKU1", "SKU2"], "qty": [10, 20]})
    excel_df.to_excel(xlsx_buf, index=False)
    xlsx_bytes = xlsx_buf.getvalue()

    payload_xlsx = {
        "documentId": "doc-xlsx1",
        "title": "Inventory Spreadsheet",
        "filename": "inventory.xlsx",
        "contentBase64": base64.b64encode(xlsx_bytes).decode(),
        "docType": "csv",
    }
    res_xlsx = client.post("/internal/documents/ingest", json=payload_xlsx, headers=_auth_headers())
    assert res_xlsx.status_code == 200
    assert res_xlsx.json()["rowCount"] == 2
