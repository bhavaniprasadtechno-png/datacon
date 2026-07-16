# Query result sanitization: hide identifier columns, fix nested-value formatting

Follow-up to `2026-07-15-chat-agent-payload-parity-design.md`'s live verification pass.
Driving a real "give leads" question against a synced MongoDB `leads` collection
surfaced two display problems in the descriptive agent's table: the raw
MongoDB `_id` column was shown to the end user, and a nested field (an
engagement/activity log) rendered as a raw Python object dump —
`ObjectId('6a0edfdfba4f8fecf9e3556f')`, `datetime.datetime(2026, 5, 21, 9, 6,
52, 493000)` — instead of anything readable.

## Root cause

`app/ai/app/connectors/service.py:51` builds a `pd.DataFrame(dataset.rows,
columns=dataset.columns)` from whatever a connector driver's `sync()`
returns, then `snapshot_store.load_dataset()` loads it into DuckDB via
`CREATE TABLE AS SELECT * FROM _incoming`. From that point on, every column
is a flat, scalar DuckDB type — there is no way to recover "this value used
to be a nested list/dict" from a query result after the fact, because the
distinction is lost the moment the driver flattens it.

That means non-scalar values can only ever be identified **at the driver**,
where the original source type is still known — not centrally. Checked all
7 connector drivers to see how much this actually matters:

- `postgres_driver.py`, `mysql_driver.py`, `sqlite_driver.py`,
  `snowflake_driver.py`: `rows = cur.fetchall()` — native driver tuples of
  flat scalars only (str/int/float/Decimal/date/datetime/bytes). No
  connector-specific handling needed; these never produce nested values.
- `http_driver.py`: rows come from `pandas.read_csv`/`read_parquet` — flat
  by construction.
- `bigquery_driver.py`, `snowflake_driver.py`: don't populate full `rows` at
  all yet (preview-only, gated behind optional cloud extras) — no risk
  today, and out of scope to wire up here.
- `mongodb_driver.py`: the **only** driver that can produce non-scalar
  values, because MongoDB documents are schemaless and can embed arrays of
  sub-documents (e.g. an `engagementLog` field). Its `_to_cell(value)`
  helper (line 34-37) currently stringifies any non-primitive value via
  plain `str()` — which is where the repr blob comes from: `str()` on a
  `list`/`dict` calls `repr()` on each contained element, so a nested
  `datetime`/`ObjectId` inside `engagementLog` shows in its constructor-call
  repr form even though the outer call was `str()`, not `repr()`.

Separately, hiding **identifier columns** (`_id`, `user_id`, `adminId`, …)
*is* fully connector-agnostic — it's a column-naming check, not a
value-type check, and column names are visible at query time regardless of
source. That part belongs centrally in `executor.py`, applied uniformly to
every connector's output.

## Fix 1 — `mongodb_driver.py`'s `_to_cell(value)`

The only driver that needs this, following a general rule any future driver
would follow too: **a driver must return `None`, not `str()`, for a value
that isn't already flat/scalar.**

```python
from datetime import date, datetime


def _to_cell(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return None
    return str(value)
```

- Primitives — unchanged.
- `datetime`/`date` — now `.isoformat()` (e.g. `"2026-05-21T09:06:52.493000"`)
  instead of falling through to `str()`. This covers *top-level* date
  fields like `createdAt`, which are simple scalars worth showing nicely.
- `list`/`dict` (nested/compound values like `engagementLog`) — now `None`.
  No attempt at recursively formatting arbitrary nested structures; that's
  unbounded scope for a field business users don't need surfaced anyway.
- Anything else unusual (e.g. a bare `ObjectId` that isn't `_id` itself) —
  unchanged, falls to `str(value)`, which already produces a clean hex
  string (confirmed by the original screenshot: the `_id` column itself
  displayed fine, it just shouldn't be shown at all — that's Fix 2).

## Fix 2 — `executor.py`'s `answer_question()`, after a successful query

A new `_filter_sensitive_columns(columns, rows)` runs right before the
success return, dropping:

- Any column whose name is `id`/`_id` (exact, case-insensitive), or ends
  with `_id` (snake_case: `user_id`, `admin_id`), `Id` (camelCase:
  `adminId`, `connectorId`), or `ID` (all-caps: `UserID`, `ConnectorID`) —
  covers Mongo's `_id` and every common SQL-style identifier/foreign-key
  naming convention uniformly, regardless of which connector produced the
  table.
- Any column where every returned row's value is `None` — this is what
  catches the columns Fix 1 just converted to `None` (nested/complex
  MongoDB fields), plus incidentally hides any genuinely-empty column.

```python
def _is_identifier_column(name: str) -> bool:
    lowered = name.lower()
    if lowered in ("id", "_id") or lowered.endswith("_id"):
        return True
    return name.endswith("Id") or name.endswith("ID")


def _filter_sensitive_columns(columns: list[str], rows: list[list]) -> tuple[list[str], list[list]]:
    keep = [
        i for i, name in enumerate(columns)
        if not _is_identifier_column(name)
        and (not rows or any(row[i] is not None for row in rows))
    ]
    filtered_columns = [columns[i] for i in keep]
    filtered_rows = [[row[i] for i in keep] for row in rows]
    return filtered_columns, filtered_rows
```

Applied once, in `answer_question()`'s success path, right after
`_execute_with_timeout` returns and the row list is capped to
`ROW_LIMIT`:

```python
columns, rows = await _execute_with_timeout(sql)
rows = rows[:ROW_LIMIT]
columns, rows = _filter_sensitive_columns(columns, rows)
return QueryAnswer(ok=True, columns=columns, rows=rows, sql=sql, message="ok")
```

Because this lives in `executor.answer_question()` — the single choke
point every agent (`descriptive`/`diagnostic`/`predictive`/`prescriptive`)
calls through — it applies uniformly with zero per-agent duplication, and
uniformly across every connector's data without any connector-specific
logic in `executor.py` itself.

`_is_identifier_column`'s suffix checks are deliberately case-sensitive for
the camelCase/all-caps forms (`name.endswith("Id")` / `endswith("ID")`, capital
letters) to avoid false-positives on ordinary words that happen to end in
lowercase "id" (e.g. `Paid`, `Solid`, `Grid`, `Valid` — none end in `"Id"` or
`"ID"` with an uppercase I, so none match). The snake_case check
(`lowered.endswith("_id")`) is safe by construction — the underscore makes
accidental matches on plain English words essentially impossible.

## Error handling

No new error surface. `_filter_sensitive_columns` operates on already
in-memory `columns`/`rows` with pure list comprehensions — no I/O, no new
failure modes. Only the previously error-handled paths (query execution
failure, LLM decline) remain as-is.

## Testing

- New `app/ai/tests/connectors/test_mongodb_driver.py` for `_to_cell`:
  primitives pass through unchanged; `datetime`/`date` → `.isoformat()`;
  `list`/`dict` → `None`; an opaque non-primitive scalar (e.g. a
  bson-`ObjectId`-shaped stand-in) → `str(value)`.
- `app/ai/tests/query_engine/test_executor.py` (existing file) gets new
  cases: a result with an `_id` column has it dropped; a `user_id`
  (snake_case) column is dropped; an `adminId` (camelCase) column is
  dropped; a `ConnectorID` (all-caps) column is dropped; a bare `id` column
  is dropped; a column where every row's value is `None` is dropped;
  ordinary columns (`name`, `email`, `revenue`, `createdAt`) survive
  untouched, including words that merely end in lowercase "id" (`Paid`,
  `Grid`) to guard against the false-positive this suffix check must avoid.
