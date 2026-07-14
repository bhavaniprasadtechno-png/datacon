import os
import sqlite3
from app.connectors.types import TestResult, SyncResult, DatasetResult

ROW_CAP = 20_000


def _connect(config: dict):
    path = config.get("path")
    if not path:
        raise ValueError("Database file path is required.")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)


def test(config: dict, secrets: dict) -> TestResult:
    path = config.get("path")
    if not path:
        return TestResult(False, "Database file path is required.")
    if not os.path.isfile(path):
        return TestResult(False, f"No file found at {path}.")
    try:
        conn = _connect(config)
        conn.execute("SELECT 1")
        conn.close()
        return TestResult(True, "Connection succeeded.")
    except Exception as e:
        return TestResult(False, f"Couldn't open database: {e}")


def sync(config: dict, secrets: dict) -> SyncResult:
    try:
        conn = _connect(config)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [r[0] for r in cur.fetchall()]
        datasets = []
        for table in tables:
            cur.execute(f'PRAGMA table_info("{table}")')
            columns = [row[1] for row in cur.fetchall()]
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            row_count = cur.fetchone()[0]
            cur.execute(f'SELECT * FROM "{table}" LIMIT {ROW_CAP}')
            rows = cur.fetchall()
            sample_rows = [[str(v) for v in row] for row in rows[:5]]
            datasets.append(DatasetResult(name=table, columns=columns, row_count=row_count, sample_rows=sample_rows, rows=rows))
        conn.close()
        return SyncResult(True, f"Discovered {len(datasets)} table(s).", datasets)
    except Exception as e:
        return SyncResult(False, f"Sync failed: {e}", [])
