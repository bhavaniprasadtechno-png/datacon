# Free-form chat grounding

Follow-up to `2026-07-13-real-data-grounding-design.md`. That spec built the query
engine (DuckDB snapshot store, NL→SQL generator, SELECT-only executor) and
grounded four *fixed* canonical questions (revenue by month, revenue by region,
tickets by day, churn snapshot) in real connected/uploaded data. In practice this
meant chat could only ever answer questions shaped like those four — a real
question like "what are total leads" or "percentage of private room in airbnb"
fell through to the honest-no-data path even when the relevant data (a synced
Mongo `leads` collection, an uploaded Airbnb CSV) was sitting right there in the
query engine, because nothing ever asked the query engine *that* question.

## Problem

1. `mongodb_driver.py`'s `sync()` was never extended to load full row data into
   the query engine (an explicit, named scope cut in the prior spec) — Mongo
   collections show up in the Unified Data Store catalog with real previews, but
   nothing from Mongo ever reaches DuckDB, so no Mongo-sourced question can ever
   ground, regardless of how many times it's synced.
2. Chat's grounding is gated on four fixed English questions
   (`MetricsService.revenueHistory/regionRevenue/ticketDaily/churnSnapshot`),
   asked once per chat turn regardless of what the user actually typed. A
   question outside that shape (leads, listings, anything not revenue/region/
   ticket/churn) never reaches the query engine at all — it's not that the
   answer comes back empty, it's that the relevant question is never asked.

## Goal

Descriptive answers the user's actual question, grounded in whatever data is
actually loaded (any synced connector, any uploaded CSV) — not restricted to a
revenue/region shape. Diagnostic/Predictive/Prescriptive keep their existing
real math (spike-vs-baseline %, OLS/Holt-Winters, churn action-list) but source
the specific data shape that math needs by asking the query engine directly,
in-process, instead of through a separate `MetricsService`-mediated layer.
`MetricsService`/`InsightsService`/`ForecastsController` are unchanged — they
still ask the four canonical questions for page-load KPIs, since a dashboard
page has no free-text question to work from.

## Mongo driver

`ai/app/connectors/drivers/mongodb_driver.py`'s `sync()` gets the same
treatment `sqlite_driver.py` got in the prior spec: fetch up to `ROW_CAP`
(20,000) documents per collection via `coll.find().limit(ROW_CAP)`, flatten
each document's values for the already-derived top-level-key column list (as
today, columns come from the first sampled document's keys — MongoDB is
schemaless, so this stays a best-effort projection, unchanged from the existing
approach), and populate `DatasetResult.rows` with the native-typed values
(not stringified — matching the prior spec's native-type-preservation
approach for other drivers, so numeric aggregation works). No change needed
in `connectors/service.py`: it already loads any driver's `.rows` into DuckDB
via `load_dataset()`/`drop_datasets()`, engine-agnostic.

## Agents ask the query engine directly

Each of `ai/app/agents/{descriptive,diagnostic,predictive,prescriptive}.py`'s
`prepare()` functions becomes `async def prepare(question: str) -> AgentPrep`
(drops the `context: dict` parameter entirely — there is no more pre-fetched
context to receive) and calls `app.query_engine.executor.answer_question(...)`
directly, in-process:

- **`descriptive.py`**: calls `answer_question(question)` with the user's
  literal question, verbatim. On `ok=True`, builds a short table-shaped
  payload (`{"columns": [...], "rows": [...]}` — a *new* payload key
  `AgentVisualization.tsx` doesn't recognize, so it renders as plain LLM
  prose with no chart, matching the "no frontend changes needed" plan) and
  has the LLM narrate the real returned rows in prose (no more region-bars
  special case; the SYSTEM prompt drops the "revenue-by-region" framing and
  becomes general-purpose: "given a real query result table, answer the
  user's question about it in one tight paragraph"). On `ok=False`, returns
  `executor`'s own `message` (e.g. "No data is connected yet." or "Couldn't
  turn that question into a query.") as the honest `offline_text` — same
  honesty guarantee as before, now covering any question, not just revenue.
- **`diagnostic.py`**: calls `answer_question("Count of events per day for
  the most relevant countable/event log, grouped and ordered chronologically,
  for the last 8 days")` — a fixed, targeted question asked by the agent
  itself, not the user's literal wording (spike-detection math needs a
  specific series shape). Existing baseline-vs-spike percentage math and
  ChromaDB RAG citation logic (`chroma_query`) are unchanged. On no data,
  same `NO_DATA_TEXT` guard as today.
- **`predictive.py`**: calls `answer_question("Total revenue for each month,
  ordered chronologically")` (the same wording `MetricsService.revenueHistory`
  used to send, now asked directly). Existing OLS/Holt-Winters forecasting
  math, existing `len(series) < 2` guard, and existing payload shape are
  unchanged — only the source of the series changes.
- **`prescriptive.py`**: calls `answer_question("The single most recent churn
  rate percentage, the previous period's churn rate percentage, and the
  number of at-risk accounts")`. Existing action-list logic and `NO_DATA_TEXT`
  guard on a falsy result are unchanged, **except** the `topIncidentTitle`
  reference is dropped: the second action's title simplifies from `f"Fix
  EMEA billing errors from {incident_title}"` to a generic `"Fix billing
  errors flagged in support documentation"` — `topIncidentTitle` was an
  `api`-side Prisma `DataSource` lookup that doesn't fit the new
  fully-self-contained-in-`ai/` model, and re-threading one leftover field
  back through a payload isn't worth the special case.

Column-matching from a query result's rows into the specific field each of
these three needs (a numeric series, a per-day count, a churn percentage) uses
the same heuristic substring-matching approach already accepted in the prior
spec's `MetricsService` (case-insensitive keyword matching over column names) —
this logic moves from TypeScript (`metrics.service.ts`) into Python
(`ai/app/query_engine/`, as a shared helper each of the three agents calls),
not duplicated three times.

## What shrinks

- `ai/app/internal/chat_router.py`'s `ChatPayload.context: dict` field is
  removed entirely — agents take no external context, only `question`.
- `api/src/chat/chat.controller.ts` stops calling
  `this.metrics.chatContext(...)` before its `POST /internal/chat/stream`
  call. The `/internal/chat/stream` request body drops `context`; `model` is
  still passed (per-request model override, unrelated to this change).
- `api/src/metrics/metrics.service.ts`'s `chatContext()` method (the
  `Promise.all` bundling all five fields for chat) is deleted — it has no
  remaining caller. Its four data methods (`revenueHistory`, `regionRevenue`,
  `ticketDaily`, `churnSnapshot`) and the two Prisma-backed ones
  (`ticketTableRowCount`, `topIncidentTitle`) are **unchanged** and keep
  serving `InsightsService`/`ForecastsController`.

## Error handling

Unchanged from the prior spec's query engine (SELECT-only validation, one
repair retry, row cap, timeout) — this spec only changes *what question* gets
asked and *who* asks it, not the engine itself. Each agent's honest-no-data
text is unchanged in spirit; wording adjusts per agent (see above) to no
longer imply "revenue" specifically when the question wasn't about revenue.

## Explicitly out of scope

- HTTP/BigQuery/Snowflake driver full-row loading (still a documented
  fast-follow, same as the prior spec).
- Any change to `InsightsService`, `ForecastsController`, or the regex router
  (`ai/app/agents/router.py`) — routing which agent(s) fire is unchanged.
- Multi-table joins or cross-dataset reasoning beyond what a single
  `answer_question` call already supports (one generated SQL query per
  agent call, as today).
