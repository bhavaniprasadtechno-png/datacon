import pandas as pd
import pytest
from app.query_engine import snapshot_store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_store.settings, "query_engine_db_path", str(tmp_path / "test.duckdb"))
    monkeypatch.setattr(snapshot_store.settings, "database_url", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    yield


def test_load_dataset_then_execute_round_trips_data():
    df = pd.DataFrame({"region": ["NA", "EMEA"], "revenue": [1.5, 2.25]})
    snapshot_store.load_dataset("t_revenue", df)

    columns, rows = snapshot_store.execute('SELECT * FROM "t_revenue" ORDER BY region')
    assert columns == ["region", "revenue"]
    assert rows == [["EMEA", 2.25], ["NA", 1.5]]


def test_load_dataset_infers_numeric_types_not_strings():
    df = pd.DataFrame({"amount": [10, 20, 30]})
    snapshot_store.load_dataset("t_amounts", df)

    columns, rows = snapshot_store.execute('SELECT SUM(amount) AS total FROM "t_amounts"')
    assert columns == ["total"]
    assert rows == [[60]]


def test_load_dataset_replaces_existing_table_on_reload():
    snapshot_store.load_dataset("t_x", pd.DataFrame({"v": [1, 2, 3]}))
    snapshot_store.load_dataset("t_x", pd.DataFrame({"v": [9]}))

    _, rows = snapshot_store.execute('SELECT * FROM "t_x"')
    assert rows == [[9]]


def test_drop_datasets_removes_only_matching_prefix():
    snapshot_store.load_dataset("conn_a_orders", pd.DataFrame({"v": [1]}))
    snapshot_store.load_dataset("conn_b_orders", pd.DataFrame({"v": [2]}))

    snapshot_store.drop_datasets("conn_a_")

    schema = snapshot_store.schema()
    assert "conn_a_orders" not in schema
    assert "conn_b_orders" in schema


def test_schema_returns_table_and_column_names():
    snapshot_store.load_dataset("t_schema", pd.DataFrame({"col_a": [1], "col_b": ["x"]}))

    schema = snapshot_store.schema()
    assert schema["t_schema"] == ["col_a", "col_b"]


def test_schema_is_empty_when_nothing_loaded():
    assert snapshot_store.schema() == {}


def test_schema_does_not_deadlock_when_postgres_reseed_finds_data(monkeypatch):
    """Regression test: schema() used to hold its lock (and an open DuckDB
    connection) while calling ensure_seeded_from_postgres(), which calls
    load_dataset() -> re-acquires the same lock and opens a second
    connection to the same file on the same thread. Whenever a postgres
    reseed actually found data, that nesting deadlocked the whole process."""
    import threading

    def fake_reseed():
        snapshot_store.load_dataset("orders", pd.DataFrame({"id": [1, 2]}))

    monkeypatch.setattr(snapshot_store, "ensure_seeded_from_postgres", fake_reseed)

    result = {}

    def call_schema():
        result["schema"] = snapshot_store.schema()

    t = threading.Thread(target=call_schema, daemon=True)
    t.start()
    t.join(timeout=5)

    assert not t.is_alive(), "schema() deadlocked re-acquiring its own lock during a postgres reseed"
    assert result["schema"] == {"orders": ["id"]}
