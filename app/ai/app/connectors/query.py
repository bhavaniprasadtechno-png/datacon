"""Safe, read-only query executor over the connector drivers.

The existing drivers only expose ``test()`` and ``sync()`` — they discover
tables and sample rows but don't accept arbitrary questions. This module
adds ``run_select`` for LIVE retrieval: the chat pipeline decides *what*
to fetch (via the LLM planner in ``agents/live_query.py``) and calls in
here to execute it against the real connector.

Safety rules enforced here (not the planner):
  * SELECT only — verified by re-building the SQL from the plan, never
    passing user text into the query body.
  * Table + column names must match a supplied catalog whitelist.
  * Filter values are passed as parameters, never string-interpolated.
  * LIMIT is hard-capped at 200 rows per call.
  * Only the SQL-family engines are supported here (sqlite, postgres,
    mysql, supabase). Mongo/HTTP/BigQuery/Snowflake are out of scope
    for this first pass — the retriever silently skips connectors it
    can't safely query.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.connectors.drivers import (
    mysql_driver,
    postgres_driver,
    sqlite_driver,
    supabase_driver,
)

_MAX_ROWS = 200
_ALLOWED_ENGINES = {"sqlite", "postgres", "supabase", "mysql"}


@dataclass
class QueryPlan:
    """The shape the LLM planner produces, then this module executes."""

    connector_id: str
    engine: str
    table: str
    columns: list[str]  # [] means "*"
    filters: list[dict]  # each: {"column": str, "op": "=|<|>|<=|>=|!=|like", "value": Any}
    order_by: str | None = None
    order_dir: str = "ASC"
    limit: int = 20


@dataclass
class QueryResult:
    ok: bool
    message: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    engine: str = ""
    table: str = ""


_ALLOWED_OPS = {"=", "<", ">", "<=", ">=", "!=", "like"}


def _validate(plan: QueryPlan, catalog: dict[str, list[str]]) -> str | None:
    """Return None if valid, else an error message. Catalog is
    ``{table_name: [column_names]}`` and defines the whitelist."""
    if plan.engine not in _ALLOWED_ENGINES:
        return f"Engine '{plan.engine}' not supported for live query."
    if plan.table not in catalog:
        return f"Table '{plan.table}' not in catalog."
    known_cols = set(catalog[plan.table])
    for c in plan.columns:
        if c not in known_cols:
            return f"Column '{c}' not in catalog for table '{plan.table}'."
    for f in plan.filters:
        if f.get("column") not in known_cols:
            return f"Filter column '{f.get('column')}' not in catalog."
        if f.get("op") not in _ALLOWED_OPS:
            return f"Filter op '{f.get('op')}' not allowed."
    if plan.order_by and plan.order_by not in known_cols:
        return f"order_by '{plan.order_by}' not in catalog."
    if plan.order_dir not in {"ASC", "DESC"}:
        return f"order_dir must be ASC or DESC."
    return None


def _build_sql(plan: QueryPlan, param_style: str) -> tuple[str, list[Any]]:
    """param_style: '?' for sqlite, '%s' for postgres/mysql. Names + ops
    are already validated by _validate; we quote identifiers with double
    quotes (backticks for mysql) and pass values through parameters."""
    quote = '`' if param_style == "%s_mysql" else '"'
    ph = "%s" if param_style.startswith("%s") else "?"

    col_sql = "*" if not plan.columns else ", ".join(f'{quote}{c}{quote}' for c in plan.columns)
    sql = f'SELECT {col_sql} FROM {quote}{plan.table}{quote}'
    params: list[Any] = []
    if plan.filters:
        clauses: list[str] = []
        for f in plan.filters:
            clauses.append(f'{quote}{f["column"]}{quote} {f["op"]} {ph}')
            params.append(f["value"])
        sql += " WHERE " + " AND ".join(clauses)
    if plan.order_by:
        sql += f' ORDER BY {quote}{plan.order_by}{quote} {plan.order_dir}'
    sql += f" LIMIT {min(plan.limit, _MAX_ROWS)}"
    return sql, params


def run_select(
    plan: QueryPlan,
    config: dict,
    secrets: dict,
    catalog: dict[str, list[str]],
) -> QueryResult:
    """Execute the plan against the given connector, enforcing all safety
    rules. Returns a QueryResult regardless of success — the caller decides
    whether to surface the error or silently skip."""
    err = _validate(plan, catalog)
    if err:
        return QueryResult(False, err, [], [], 0, plan.engine, plan.table)

    try:
        if plan.engine in ("sqlite",):
            sql, params = _build_sql(plan, "?")
            conn = sqlite_driver._connect(config)
            cur = conn.cursor()
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(_MAX_ROWS)]
            conn.close()
        elif plan.engine in ("postgres", "supabase"):
            sql, params = _build_sql(plan, "%s")
            driver = postgres_driver if plan.engine == "postgres" else supabase_driver
            conn = driver._connect(config, secrets)
            cur = conn.cursor()
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(_MAX_ROWS)]
            conn.close()
        elif plan.engine == "mysql":
            sql, params = _build_sql(plan, "%s_mysql")
            conn = mysql_driver._connect(config, secrets)
            cur = conn.cursor()
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(_MAX_ROWS)]
            conn.close()
        else:
            return QueryResult(False, f"Unsupported engine '{plan.engine}'.", [], [], 0, plan.engine, plan.table)
    except Exception as e:
        return QueryResult(False, f"Query failed: {e}", [], [], 0, plan.engine, plan.table)

    return QueryResult(True, "ok", cols, rows, len(rows), plan.engine, plan.table)
