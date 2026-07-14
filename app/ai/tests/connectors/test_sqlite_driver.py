import sqlite3

import pytest
from app.connectors.drivers import sqlite_driver


@pytest.fixture
def sample_db(tmp_path):
    path = str(tmp_path / "sample.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE orders (id INTEGER, revenue REAL)")
    conn.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 10.5), (2, 20.0), (3, 5.25)])
    conn.commit()
    conn.close()
    return path


def test_sync_returns_full_rows_alongside_the_five_row_sample(sample_db):
    result = sqlite_driver.sync({"path": sample_db}, {})

    assert result.ok is True
    dataset = next(d for d in result.datasets if d.name == "orders")
    assert dataset.row_count == 3
    assert len(dataset.sample_rows) == 3  # fewer than 5 rows exist, sample = all of them
    assert dataset.rows is not None
    assert len(dataset.rows) == 3
    assert dataset.rows[0][1] == 10.5  # native float, not "10.5" string


def test_sync_caps_full_rows_at_row_cap(sample_db, monkeypatch):
    monkeypatch.setattr(sqlite_driver, "ROW_CAP", 2)
    result = sqlite_driver.sync({"path": sample_db}, {})

    dataset = next(d for d in result.datasets if d.name == "orders")
    assert len(dataset.rows) == 2
    assert dataset.row_count == 3  # true count is unaffected by the cap
