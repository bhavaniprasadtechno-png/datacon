from unittest.mock import patch

import pandas as pd
import pytest
from app.connectors import service as connectors_service
from app.connectors.types import DatasetResult, SyncResult
from app.query_engine import snapshot_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    yield


def _fake_sync_result():
    return SyncResult(
        True,
        "Discovered 1 table(s).",
        [DatasetResult(name="orders", columns=["id", "revenue"], row_count=2, sample_rows=[["1", "10.0"]], rows=[(1, 10.0), (2, 20.0)])],
    )


def test_sync_connector_loads_rows_into_duckdb_when_connector_id_given():
    with patch.object(connectors_service.sqlite_driver, "sync", return_value=_fake_sync_result()):
        connectors_service.sync_connector("sqlite", {"path": "x"}, {}, connector_id="conn123")

    columns, rows = snapshot_store.execute('SELECT * FROM "conn_conn123_orders" ORDER BY id')
    assert columns == ["id", "revenue"]
    assert rows == [[1, 10.0], [2, 20.0]]


def test_sync_connector_drops_stale_tables_from_a_previous_sync():
    snapshot_store.load_dataset("conn_conn123_old_table", pd.DataFrame({"v": [1]}))

    with patch.object(connectors_service.sqlite_driver, "sync", return_value=_fake_sync_result()):
        connectors_service.sync_connector("sqlite", {"path": "x"}, {}, connector_id="conn123")

    assert "conn_conn123_old_table" not in snapshot_store.schema()
    assert "conn_conn123_orders" in snapshot_store.schema()


def test_sync_connector_without_connector_id_does_not_touch_duckdb():
    with patch.object(connectors_service.sqlite_driver, "sync", return_value=_fake_sync_result()):
        connectors_service.sync_connector("sqlite", {"path": "x"}, {})

    assert snapshot_store.schema() == {}


def test_sync_connector_skips_datasets_with_no_full_rows():
    result_without_rows = SyncResult(True, "ok", [DatasetResult(name="preview_only", columns=["a"], row_count=1, sample_rows=[["x"]], rows=None)])
    with patch.object(connectors_service.sqlite_driver, "sync", return_value=result_without_rows):
        connectors_service.sync_connector("sqlite", {"path": "x"}, {}, connector_id="conn123")

    assert snapshot_store.schema() == {}
