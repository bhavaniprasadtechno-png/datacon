# Ground Datacon's data plane in real connected/uploaded data

Spec 1 of 3 in the "fix the chat implementation" effort. Spec 2 (real predictive/diagnostic
reasoning) and Spec 3 (routing/orchestration) are separate, later specs and are explicitly
out of scope here.

## Problem

Datacon's four chat agents (`ai/app/agents/{descriptive,diagnostic,predictive,prescriptive}.py`),
`InsightsPage`, and `ForecastsPage` all read from four seeded Prisma tables —
`RevenueMetric`, `RegionRevenue`, `TicketDaily`, `ChurnSnapshot` — through one shared
`api/src/metrics/metrics.service.ts`, regardless of what the user has actually connected
(via `api/src/connectors`) or uploaded (via `api/src/documents`).

Connector syncs and CSV uploads already produce real metadata and a 5-row preview
(`UnifiedDataset`, `DataSource`), but nothing downstream ever queries that data. The chat
"grounding" the user sees is entirely computed over fixed seed data, not whatever they
actually connected.

## Goal

Replace the seeded-table data plane with a real local query engine over whatever the user
has actually connected/uploaded. No fallback to seeded/fake numbers anywhere: if nothing is
connected, features show an honest empty/no-data state (already a supported pattern —
`InsightsService.get()` already returns `forecast: null` on failure today).

The *reasoning quality* on top of that data plane is unchanged in this spec: the existing
OLS/Holt-Winters forecasting math, the existing spike-vs-baseline diagnostic math, the
existing RAG citation logic, and the existing regex-cascade router all stay exactly as they
are today. Only their **data source** changes, from fixed seed tables to real data. Spec 2
upgrades the math/reasoning; spec 3 upgrades routing.

## Architecture

New `ai/app/query_engine/` module:

- **`snapshot_store.py`** — a single local DuckDB file (`ai/data/snapshot.duckdb`; same
  ephemeral-on-redeploy tradeoff the app already accepts for ChromaDB). `load_dataset(name,
  columns, rows)` does a full-refresh table load (drop + recreate) on every sync/ingest —
  not incremental. Row count is capped (~20,000 rows/table) to bound memory on the free-tier
  host.
- **`generator.py`** — one LLM call: given a natural-language question and the current
  DuckDB schema (table/column names currently loaded), produce a single read-only SQL query.
  When no LLM API key is configured, this degrades to an honest schema/row-count/sample
  summary instead of a fabricated answer — consistent with how `offline_client.py` already
  handles the other agents.
- **`executor.py`** — validates the generated SQL is SELECT-only (rejects multi-statement,
  DDL/DML, `ATTACH`/`COPY`), runs it with a timeout, caps returned rows. On a DuckDB
  execution error, one repair retry: feed the error + original SQL back to `generator.py`
  once for a corrected query. This is a capped version of the reference implementation's
  `FixerAgent` (`D:\DataCon-AI\apps\ai-service\agents\fixer.py`), not its full retry loop.

Because SQL only ever runs against Datacon's own local DuckDB snapshot — never against a
customer's live connected system — there's no injection/blast-radius risk against
production infrastructure. Worst case is corrupting Datacon's own local copy, which
SELECT-only validation prevents regardless.

## Data plane changes

- **Connector drivers** (`ai/app/connectors/drivers/{sqlite,postgres,mysql}_driver.py` —
  the SQL-native ones): currently fetch `LIMIT 5` for the preview. Extend to also fetch up
  to the row cap and call `load_dataset()`. Mongo/HTTP/BigQuery/Snowflake drivers keep
  today's preview-only behavior for now; they share the same `SyncResult`/`DatasetResult`
  interface, so wiring them into `load_dataset()` is an interface-compatible fast-follow,
  not a redesign.
- **CSV data sources** (`ai/app/internal/documents_router.py` → `parse_csv`): currently
  returns only a 5-row preview with nothing persisted. Full parsed rows also go to
  `load_dataset()`.
- **PDF/TXT/MD documents**: unchanged. These already index real chunks into ChromaDB and
  Diagnostic already cites them correctly — this path isn't actually broken today.

## Consumers migrated onto the query engine

- **`MetricsService`** (`api/src/metrics/metrics.service.ts`) stops querying
  `RevenueMetric`/`RegionRevenue`/`TicketDaily`/`ChurnSnapshot`. Each of its methods
  (`revenueHistory`, `regionRevenue`, `ticketDaily`, `churnSnapshot`) becomes a canonical
  NL→SQL question sent to the query engine (e.g. "total revenue by month across connected
  data"), returning `null`/empty when no loaded dataset has a recognizable match.
  `topIncidentTitle` and `ticketTableRowCount` are unchanged — they already read
  `DataSource`/`UnifiedDataset` directly, not seeded tables.
- **Chat agents** (`descriptive.py`, `diagnostic.py`, `predictive.py`, `prescriptive.py`):
  same `AgentPrep` interface and same downstream math as today. Their input facts now come
  from the migrated `MetricsService` instead of seeded context. When a required metric comes
  back empty, the agent's `offline_text`/prompt says so honestly (e.g. "no revenue data is
  connected yet") instead of computing over missing data.
- **`InsightsService.get()`** and **`ai/app/internal/forecast_router.py`**: same consumers
  of `MetricsService` as today. KPI cards and the forecast chart show an empty/no-data state
  when nothing is connected — the existing `forecast: null` pattern already covers this.

## Removed

- `RevenueMetric`, `RegionRevenue`, `TicketDaily`, `ChurnSnapshot` Prisma models, plus a
  migration to drop the corresponding tables.
- The portions of `packages/prisma/seed.ts` that seed those four tables. The rest of
  seeding (users/roles/permissions/connectors/catalog tables/documents) is unrelated setup
  data, not fake computed metrics, and stays.
- `seed_chroma.py`'s two seed documents are **not** removed — they're genuinely indexed and
  cited by Diagnostic via ChromaDB, not computed-over fake tables, so they're example
  content rather than the "canned answers" problem this spec addresses.

## Error handling

- Sync/ingest fetch errors: unchanged behavior (`SyncResult.success=False`); the dataset
  simply doesn't get loaded into the query engine.
- SQL generation/execution failures: one repair retry, then an honest "couldn't answer that
  from connected data" response rather than a crash or a fabricated number.
- Executor timeout guards against a runaway generated query.

## Explicitly out of scope (future specs)

- **Spec 2**: real predictive/diagnostic reasoning — replacing the templated
  OLS/Holt-Winters commentary and spike-vs-baseline math with real forecasting/anomaly
  reasoning. Same data plane from this spec, smarter math on top.
- **Spec 3**: routing/orchestration — replacing the regex cascade
  (`ai/app/agents/router.py`) with smarter agent selection. Same data plane, smarter
  routing.
- Non-SQL connector drivers' full-row fetch (Mongo/HTTP/BigQuery/Snowflake).
- A column-to-business-concept mapping UI. V1 relies on the LLM inferring which columns
  represent revenue/region/date/etc. from real column names. If that proves unreliable in
  practice, a manual mapping step is a natural follow-up — not part of this spec.
