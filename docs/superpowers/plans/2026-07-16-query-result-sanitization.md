# Query Result Sanitization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chat answers never surface raw internal identifier columns (`_id`, `user_id`, `adminId`, `ConnectorID`, …) or unreadable Python object-repr blobs (nested MongoDB fields like an engagement log) to the end user.

**Architecture:** Two independent, connector-scoped fixes. `mongodb_driver.py`'s `_to_cell()` — the only driver that can ever produce non-scalar values, per a full audit of all 7 connector drivers — stops stringifying nested `list`/`dict` values into repr blobs (returns `None` instead) and formats `datetime`/`date` values as clean ISO strings. `executor.py`'s `answer_question()` — the single choke point every one of the four chat agents calls through — drops identifier-named columns and all-null columns from every successful query result, regardless of which connector produced the data.

**Tech Stack:** Python, pytest + pytest-asyncio, pandas, DuckDB.

## Global Constraints

- A driver must return `None`, not `str()`, for a value that isn't already flat/scalar — this is the general rule `mongodb_driver.py` follows; no other driver needs it today (Postgres/MySQL/SQLite/Snowflake return native scalar tuples only; the CSV/HTTP driver reads flat CSV/Parquet; BigQuery/Snowflake don't populate full `rows` yet).
- Identifier-column detection is name-based, not connector-specific, and lives once in `executor.py`: exact `id`/`_id` (case-insensitive), or a name ending in `_id` (snake_case), `Id` (camelCase), or `ID` (all-caps) — checked with case-sensitive suffix comparisons for the last two so ordinary words ending in lowercase "id" (`Paid`, `Solid`, `Grid`, `Valid`) are never false-positived.
- Python test command (run from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/ -v`

---

### Task 1: `mongodb_driver.py`'s `_to_cell` — format dates, drop nested values

**Files:**
- Modify: `app/ai/app/connectors/drivers/mongodb_driver.py` (imports + `_to_cell`, lines 1-37)
- Create: `app/ai/tests/connectors/test_mongodb_driver.py`

**Interfaces:**
- Produces: `_to_cell(value) -> str | int | float | bool | None` — used only by this module's own `sync()` (unchanged call site, line 60: `rows = [tuple(_to_cell(doc.get(c)) for c in columns) for doc in docs]`). No other file imports `_to_cell`.

- [ ] **Step 1: Write the failing tests**

Create `app/ai/tests/connectors/test_mongodb_driver.py`:

```python
from datetime import date, datetime

from app.connectors.drivers.mongodb_driver import _to_cell


class _FakeObjectId:
    def __str__(self):
        return "abc123"


def test_primitives_pass_through_unchanged():
    assert _to_cell(None) is None
    assert _to_cell("hello") == "hello"
    assert _to_cell(42) == 42
    assert _to_cell(3.14) == 3.14
    assert _to_cell(True) is True


def test_datetime_formats_as_clean_iso_string():
    assert _to_cell(datetime(2026, 5, 21, 9, 6, 52, 493000)) == "2026-05-21T09:06:52.493000"


def test_date_formats_as_clean_iso_string():
    assert _to_cell(date(2026, 5, 21)) == "2026-05-21"


def test_list_becomes_none_instead_of_a_repr_blob():
    assert _to_cell([{"type": "note", "createdAt": datetime(2026, 5, 21)}]) is None


def test_dict_becomes_none_instead_of_a_repr_blob():
    assert _to_cell({"a": 1}) is None


def test_other_non_primitive_scalars_still_stringify():
    assert _to_cell(_FakeObjectId()) == "abc123"
```

- [ ] **Step 2: Run tests, confirm they fail**

Run (from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/connectors/test_mongodb_driver.py -v`
Expected: FAIL — `test_datetime_formats_as_clean_iso_string` and `test_date_formats_as_clean_iso_string` fail because the current `_to_cell` falls through to `str(value)` (producing `"2026-05-21 09:06:52.493000"` for datetime, missing the `T` separator, and Python's default `date.__str__` actually already matches ISO format for dates so that one may pass — the two that must fail are the `list`/`dict` cases: `test_list_becomes_none_instead_of_a_repr_blob` and `test_dict_becomes_none_instead_of_a_repr_blob` currently get a stringified repr, not `None`).

- [ ] **Step 3: Replace `app/ai/app/connectors/drivers/mongodb_driver.py` lines 1-37**

```python
import logging
from datetime import date, datetime
from pymongo import MongoClient
from app.connectors.types import TestResult, SyncResult, DatasetResult

ROW_CAP = 20_000

logger = logging.getLogger("app.connectors.drivers.mongodb")


def _client(secrets: dict) -> MongoClient:
    uri = secrets.get("uri")
    if not uri:
        raise ValueError("Connection URI is required.")
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def test(config: dict, secrets: dict) -> TestResult:
    db_name = config.get("database")
    logger.info("[MongoDB] Testing connection for database '%s'...", db_name)
    if not secrets.get("uri") or not db_name:
        logger.warning("[MongoDB] Connection test failed: missing URI or database in config.")
        return TestResult(False, "Connection URI and database are required.")
    try:
        client = _client(secrets)
        client.admin.command("ping")
        client.close()
        logger.info("[MongoDB] Connection test succeeded.")
        return TestResult(True, "Connection succeeded.")
    except Exception as e:
        logger.exception("[MongoDB] Connection test failed: %s", e)
        return TestResult(False, f"Couldn't connect: {e}")


def _to_cell(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return None
    return str(value)
```

(Leave `sync()`, further down in the file, untouched — only the imports and `_to_cell` change.)

- [ ] **Step 4: Run tests, confirm they pass**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/connectors/test_mongodb_driver.py -v`
Expected: 6 passed.

- [ ] **Step 5: Stage and draft commit message (do not commit without user go-ahead)**

Per this repo's convention (CLAUDE.md forbids committing without explicit ask): leave the change unstaged in the working tree.
Draft message for later: `fix(mongodb): format dates as ISO strings, drop nested values instead of stringifying them`

---

### Task 2: `executor.py` — drop identifier and all-null columns from every query result

**Files:**
- Modify: `app/ai/app/query_engine/executor.py` (new helpers + the success-path return, lines 58-67)
- Modify: `app/ai/tests/query_engine/test_executor.py` (append new test cases)

**Interfaces:**
- Consumes: nothing new — operates on the `columns: list[str]`, `rows: list[list]` already produced by `_execute_with_timeout()`.
- Produces: `_is_identifier_column(name: str) -> bool`, `_filter_sensitive_columns(columns: list[str], rows: list[list]) -> tuple[list[str], list[list]]` — both private to `executor.py`, not consumed elsewhere. `answer_question()`'s return shape (`QueryAnswer`) is unchanged; only its `columns`/`rows` content is now filtered.

- [ ] **Step 1: Write the failing tests**

Append to `app/ai/tests/query_engine/test_executor.py`:

```python
@pytest.mark.asyncio
async def test_drops_the_mongo_style_id_column():
    snapshot_store.load_dataset("leads", pd.DataFrame({"_id": ["abc123"], "name": ["Jane"]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT _id, name FROM leads")):
        result = await executor.answer_question("give leads")
    assert result.columns == ["name"]
    assert result.rows == [["Jane"]]


@pytest.mark.asyncio
async def test_drops_snake_case_camel_case_and_allcaps_id_columns():
    snapshot_store.load_dataset(
        "leads",
        pd.DataFrame({"user_id": [1], "adminId": [2], "ConnectorID": [3], "id": [4], "name": ["Jane"]}),
    )
    with patch.object(
        executor.generator,
        "generate_sql",
        new=AsyncMock(return_value="SELECT user_id, adminId, ConnectorID, id, name FROM leads"),
    ):
        result = await executor.answer_question("give leads")
    assert result.columns == ["name"]
    assert result.rows == [["Jane"]]


@pytest.mark.asyncio
async def test_keeps_ordinary_columns_that_merely_end_in_lowercase_id():
    snapshot_store.load_dataset("leads", pd.DataFrame({"Paid": [True], "Grid": ["A1"]}))
    with patch.object(executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT Paid, Grid FROM leads")):
        result = await executor.answer_question("give leads")
    assert result.columns == ["Paid", "Grid"]
    assert result.rows == [[True, "A1"]]


@pytest.mark.asyncio
async def test_drops_a_column_where_every_row_is_null():
    snapshot_store.load_dataset(
        "leads",
        pd.DataFrame({"engagementLog": [None, None], "name": ["Jane", "Ashwarya"]}),
    )
    with patch.object(
        executor.generator, "generate_sql", new=AsyncMock(return_value="SELECT engagementLog, name FROM leads")
    ):
        result = await executor.answer_question("give leads")
    assert result.columns == ["name"]
    assert result.rows == [["Jane"], ["Ashwarya"]]
```

- [ ] **Step 2: Run tests, confirm they fail**

Run (from `app/ai`): `"./.venv/Scripts/python.exe" -m pytest tests/query_engine/test_executor.py -k "drops_the_mongo or drops_snake or keeps_ordinary or drops_a_column_where" -v`
Expected: FAIL — all four new tests fail because `answer_question` currently returns every column the SQL selected, unfiltered (e.g. `test_drops_the_mongo_style_id_column` expects `result.columns == ["name"]` but gets `["_id", "name"]`).

- [ ] **Step 3: Add the two helper functions to `app/ai/app/query_engine/executor.py`**

Insert immediately before `async def answer_question(...)`:

```python
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
```

- [ ] **Step 4: Apply the filter in the success path**

Replace:
```python
        try:
            logger.info("[Executor] Executing SQL against DuckDB...")
            columns, rows = await _execute_with_timeout(sql)
            logger.info("[Executor] Query execution succeeded. Row count: %s", len(rows))
            return QueryAnswer(ok=True, columns=columns, rows=rows[:ROW_LIMIT], sql=sql, message="ok")
```
with:
```python
        try:
            logger.info("[Executor] Executing SQL against DuckDB...")
            columns, rows = await _execute_with_timeout(sql)
            logger.info("[Executor] Query execution succeeded. Row count: %s", len(rows))
            columns, rows = _filter_sensitive_columns(columns, rows[:ROW_LIMIT])
            return QueryAnswer(ok=True, columns=columns, rows=rows, sql=sql, message="ok")
```

- [ ] **Step 5: Run tests, confirm they pass**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/query_engine/test_executor.py -v`
Expected: all tests in this file pass (12 total: 8 existing + 4 new).

- [ ] **Step 6: Run the full backend suite**

Run: `"./.venv/Scripts/python.exe" -m pytest tests/ -v`
Expected: 61 passed (51 before this plan + 6 new in `test_mongodb_driver.py` from Task 1 + 4 new in `test_executor.py` from this task).

- [ ] **Step 7: Stage and draft commit message (do not commit without user go-ahead)**

Leave unstaged, per this repo's convention.
Draft message for later: `fix(query-engine): drop identifier and all-null columns from chat query results`

---

### Task 3: Manual verification against the live app

**Files:** none (verification only).

- [ ] **Step 1: Restart the `ai` dev service** so it picks up both changes (or rely on `--reload` if already running that way).

- [ ] **Step 2: Ask a descriptive question that previously showed `_id` and a nested field**, e.g. "give leads", against the same synced MongoDB `leads` collection used in the original bug report.

- [ ] **Step 3: Confirm in the rendered table:**
- No `_id` column (or any other identifier-named column) appears.
- No column shows a raw Python repr blob (`ObjectId(...)`, `datetime.datetime(...)`, a stringified list of dicts).
- Ordinary business columns (`name`, `email`, `status`, etc.) still render normally.
- If the source data has a genuine top-level date field, confirm it now shows as a clean ISO string rather than a Python repr.
