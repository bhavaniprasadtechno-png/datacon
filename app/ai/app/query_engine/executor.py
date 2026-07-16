import asyncio
import re
import logging
from dataclasses import dataclass

from app.query_engine import generator, snapshot_store

logger = logging.getLogger("app.query_engine.executor")

_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|COPY|EXPORT|PRAGMA|CALL|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

ROW_LIMIT = 500
QUERY_TIMEOUT_SECONDS = 10


@dataclass
class QueryAnswer:
    ok: bool
    columns: list[str]
    rows: list[list]
    sql: str | None
    message: str


def _is_safe_select(sql: str) -> bool:
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    if len(statements) != 1:
        return False
    single = statements[0]
    if not re.match(r"^\s*(SELECT|WITH)\b", single, re.IGNORECASE):
        return False
    return not _WRITE_KEYWORDS.search(single)


async def _execute_with_timeout(sql: str) -> tuple[list[str], list[list]]:
    return await asyncio.wait_for(asyncio.to_thread(snapshot_store.execute, sql), timeout=QUERY_TIMEOUT_SECONDS)


def _is_identifier_column(name: str) -> bool:
    lowered = name.lower()
    if lowered in ("id", "_id") or lowered.endswith("_id"):
        return True
    return name.endswith("Id") or name.endswith("ID")


def _filter_sensitive_columns(columns: list[str], rows: list[list]) -> tuple[list[str], list[list]]:
    """Drop internal identifier columns (_id, id, *_id, *Id, *ID) and columns
    that are entirely null (nested/complex MongoDB values are flattened to
    None at sync time — see mongodb_driver.py's _to_cell — rather than
    surfaced as raw Python object reprs)."""
    keep = [
        i for i, name in enumerate(columns)
        if not _is_identifier_column(name)
        and (not rows or any(row[i] is not None for row in rows))
    ]
    filtered_columns = [columns[i] for i in keep]
    filtered_rows = [[row[i] for i in keep] for row in rows]
    return filtered_columns, filtered_rows


async def answer_question(question: str, model: str | None = None) -> QueryAnswer:
    logger.info("[Executor] Received question to answer: '%s'", question)
    schema = snapshot_store.schema()
    if not schema:
        logger.warning("[Executor] Schema is empty. No datasets are loaded. Short-circuiting.")
        return QueryAnswer(ok=False, columns=[], rows=[], sql=None, message="No data is connected yet.")

    logger.info("[Executor] Schema discovered with %s table(s): %s", len(schema), list(schema.keys()))
    logger.info("[Executor] Generating SQL from natural language question...")
    sql = await generator.generate_sql(question, schema, model=model)
    if not sql:
        logger.warning("[Executor] LLM failed to generate SQL for the question: '%s'", question)
        return QueryAnswer(ok=False, columns=[], rows=[], sql=None, message="Couldn't turn that question into a query.")

    logger.info("[Executor] Generated SQL: %s", sql.strip())

    for attempt in range(2):
        logger.info("[Executor] Run attempt %s/2...", attempt + 1)
        if not _is_safe_select(sql):
            logger.warning("[Executor] Rejected SQL because it is not a safe read-only single SELECT statement.")
            return QueryAnswer(ok=False, columns=[], rows=[], sql=sql, message="Generated query was rejected (not a read-only SELECT).")
        try:
            logger.info("[Executor] Executing SQL against DuckDB...")
            columns, rows = await _execute_with_timeout(sql)
            logger.info("[Executor] Query execution succeeded. Row count: %s", len(rows))
            columns, rows = _filter_sensitive_columns(columns, rows[:ROW_LIMIT])
            return QueryAnswer(ok=True, columns=columns, rows=rows, sql=sql, message="ok")
        except Exception as e:
            logger.warning("[Executor] Query attempt %s failed with error: %s", attempt + 1, e)
            if attempt == 0:
                logger.info("[Executor] Prompting LLM to repair the broken SQL...")
                sql = await generator.generate_sql(question, schema, error_context=f"SQL: {sql}\nError: {e}", model=model)
                if not sql:
                    logger.warning("[Executor] LLM failed to generate repaired SQL.")
                    return QueryAnswer(ok=False, columns=[], rows=[], sql=None, message=f"Query failed: {e}")
                logger.info("[Executor] Repaired SQL generated: %s", sql.strip())
                continue
            logger.error("[Executor] Query failed after retry: %s", e)
            return QueryAnswer(ok=False, columns=[], rows=[], sql=sql, message=f"Query failed after retry: {e}")

    return QueryAnswer(ok=False, columns=[], rows=[], sql=sql, message="Query failed.")


async def grouped_count(base_sql: str, column: str) -> QueryAnswer:
    """Wraps an already-validated SELECT (the exact SQL answer_question just
    ran, available as QueryAnswer.sql) as a GROUP BY/COUNT subquery — no LLM
    call, guaranteed to run against the exact same rows the original query
    produced."""
    inner = base_sql.strip().rstrip(";")
    wrapped = (
        f'SELECT "{column}" AS label, COUNT(*) AS value\n'
        f"FROM ({inner}) AS _dc_dist\n"
        f'GROUP BY "{column}"\n'
        "ORDER BY value DESC\n"
        "LIMIT 20"
    )
    if not _is_safe_select(wrapped):
        return QueryAnswer(ok=False, columns=[], rows=[], sql=wrapped, message="Generated query was rejected (not a read-only SELECT).")
    try:
        columns, rows = await _execute_with_timeout(wrapped)
        return QueryAnswer(ok=True, columns=columns, rows=rows, sql=wrapped, message="ok")
    except Exception as e:
        logger.warning("[Executor] grouped_count query failed: %s", e)
        return QueryAnswer(ok=False, columns=[], rows=[], sql=wrapped, message=f"Grouped count query failed: {e}")

