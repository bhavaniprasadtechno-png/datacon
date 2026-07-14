"""Local DuckDB snapshot of whatever the user has actually connected
(SQL-native connectors) or uploaded (CSV data sources). Every load is a
full refresh — DuckDB is a disposable local cache of real external data,
not a system of record, so there's no incremental-update complexity here.
"""
import os
import threading
import logging
import duckdb
import pandas as pd

from app.config import settings

logger = logging.getLogger("app.query_engine.snapshot_store")
_lock = threading.Lock()


def _connect() -> duckdb.DuckDBPyConnection:
    path = settings.query_engine_db_path
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return duckdb.connect(path)


def load_dataset(name: str, df: pd.DataFrame) -> None:
    """Replaces any existing table named `name` with `df`'s data, with
    column types inferred from the DataFrame rather than forced to text."""
    logger.info("[DuckDB] Loading dataset '%s' into DuckDB. Rows: %s, Columns: %s", name, len(df), list(df.columns))
    with _lock:
        conn = _connect()
        try:
            conn.register("_incoming", df)
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')
            conn.execute(f'CREATE TABLE "{name}" AS SELECT * FROM _incoming')
            conn.unregister("_incoming")
            logger.info("[DuckDB] Dataset '%s' successfully loaded.", name)
        except Exception as e:
            logger.exception("[DuckDB] Failed to load dataset '%s'", name)
            raise e
        finally:
            conn.close()


def drop_datasets(prefix: str) -> None:
    """Drops every table whose name starts with `prefix` — used before a
    connector resync, since the current sync's discovered table set can
    differ from the last one."""
    logger.info("[DuckDB] Dropping datasets with prefix: '%s'", prefix)
    with _lock:
        conn = _connect()
        try:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_name LIKE ?",
                [f"{prefix}%"],
            ).fetchall()
            for (table_name,) in tables:
                logger.info("[DuckDB] Dropping table '%s'", table_name)
                conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        except Exception as e:
            logger.exception("[DuckDB] Failed to drop datasets with prefix '%s'", prefix)
            raise e
        finally:
            conn.close()


def schema() -> dict[str, list[str]]:
    """Table name -> column names, for every table currently loaded."""
    with _lock:
        conn = _connect()
        try:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
            out: dict[str, list[str]] = {}
            for (table_name,) in tables:
                cols = conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = ? ORDER BY ordinal_position",
                    [table_name],
                ).fetchall()
                out[table_name] = [c[0] for c in cols]
            return out
        finally:
            conn.close()


def execute(sql: str) -> tuple[list[str], list[list]]:
    """Runs `sql` (assumed already validated as read-only by the caller)
    and returns (column_names, rows)."""
    logger.info("[DuckDB] Executing SQL: %s", sql)
    with _lock:
        conn = _connect()
        try:
            result = conn.execute(sql)
            columns = [d[0] for d in result.description]
            rows = [list(r) for r in result.fetchall()]
            logger.info("[DuckDB] SQL execution succeeded. Returned %s columns, %s rows.", len(columns), len(rows))
            return columns, rows
        except Exception as e:
            logger.exception("[DuckDB] SQL execution failed: %s", sql)
            raise e
        finally:
            conn.close()

