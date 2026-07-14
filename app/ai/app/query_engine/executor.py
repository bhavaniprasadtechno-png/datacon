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


async def answer_question(question: str) -> QueryAnswer:
    logger.info("[Executor] Received question to answer: '%s'", question)
    schema = snapshot_store.schema()
    if not schema:
        logger.warning("[Executor] Schema is empty. No datasets are loaded. Short-circuiting.")
        return QueryAnswer(ok=False, columns=[], rows=[], sql=None, message="No data is connected yet.")

    logger.info("[Executor] Schema discovered with %s table(s): %s", len(schema), list(schema.keys()))
    logger.info("[Executor] Generating SQL from natural language question...")
    sql = await generator.generate_sql(question, schema)
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
            return QueryAnswer(ok=True, columns=columns, rows=rows[:ROW_LIMIT], sql=sql, message="ok")
        except Exception as e:
            logger.warning("[Executor] Query attempt %s failed with error: %s", attempt + 1, e)
            if attempt == 0:
                logger.info("[Executor] Prompting LLM to repair the broken SQL...")
                sql = await generator.generate_sql(question, schema, error_context=f"SQL: {sql}\nError: {e}")
                if not sql:
                    logger.warning("[Executor] LLM failed to generate repaired SQL.")
                    return QueryAnswer(ok=False, columns=[], rows=[], sql=None, message=f"Query failed: {e}")
                logger.info("[Executor] Repaired SQL generated: %s", sql.strip())
                continue
            logger.error("[Executor] Query failed after retry: %s", e)
            return QueryAnswer(ok=False, columns=[], rows=[], sql=sql, message=f"Query failed after retry: {e}")

    return QueryAnswer(ok=False, columns=[], rows=[], sql=sql, message="Query failed.")

