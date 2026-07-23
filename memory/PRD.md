# Datacon — PRD & Change Log

## Original problem statements (all satisfied)
- Fix chat, make agents dynamic to question + data.
- System shall give accurate answers and reports based on user questions.
- Cache the router LLM call per (question, schema).
- E2E validate on running stack with real TOGETHER_API_KEY.
- Multi-agent Retriever → Analyst → Validator → Responder pipeline.
- **Extend retriever to run LIVE queries via connectors when a question needs data outside the pre-computed metrics blob.**

## Architecture
- `web/` — React 19 + Vite chat UI (streams SSE from `api/chat/stream`)
- `api/` — NestJS controller: appends messages to Prisma, proxies SSE
- `ai/` — FastAPI, multi-agent pipeline:
  **Retriever (pre-computed + LIVE query) → Router (cached LLM) → Analytical modes → Validator → Responder (single streamed LLM)**
- Data: Postgres (Prisma) + ChromaDB (RAG) + LIVE connector querying (sqlite/postgres/supabase/mysql)

## Live query capability (this session)
### New modules
- **`connectors/query.py`** — Safe SELECT executor over the existing
  driver connections. Enforces:
  - Table + column whitelist supplied by caller (from catalog).
  - Filter values passed as query parameters (`?` / `%s`), never
    string-interpolated.
  - Only `= < > <= >= != like` filter ops accepted.
  - `LIMIT` hard-capped at 200 rows.
  - Only sqlite / postgres / supabase / mysql engines. Mongo /
    BigQuery / Snowflake / HTTP are silently skipped (out of scope).
- **`agents/live_query.py`** — LLM query planner. Given the question +
  catalog, produces a `QueryPlan {connector_id, engine, table, columns,
  filters, order_by, order_dir, limit, why}`. Returns `None` when the
  question can be answered from the pre-computed blob (`needed: false`),
  the LLM is unreachable, or the reply is unparseable.
- **`agents/retriever.py`** — new `retrieve_async` variant that runs the
  planner + executor when the caller passes `context.catalog` +
  `context.connectors`. Falls back to the previous pre-computed-only
  path when either is absent. `live_facts` is added to the bundle and
  tagged with `"Live: <table>"` in the `sources` list.

### Chat pipeline & UI
- **`internal/chat_router.py`** — awaits `retrieve_async`; emits
  `retriever_done` with `live_query_count` and `live_query_run` for the
  frontend reasoning panel.
- **`agents/responder.py`** — LLM prompt + offline template now include
  `Live[engine].table (row_count rows, cols=…)` alongside DB / Doc
  facts so answers can cite live rows.
- `agent_done.payload.details.retriever.live_facts` carries the row set
  for the frontend "Show reasoning" panel.

### Context contract (documented for NestJS to populate)
The AI service now consumes an OPTIONAL extension to `chatContext`:
```
context.catalog:    [ {connector_id, engine, table, columns, row_count}, ... ]
context.connectors: { <connector_id>: {config: {...}, secrets: {...}} }
```
When absent, the retriever behaves exactly as before. When present, the
LLM planner decides per turn whether a live query is warranted.

## Verified this session
### Unit tests (in-memory SQLite)
- Executor with a valid plan returns the exact expected rows sorted correctly.
- SQL-injection attempt via a crafted column name → rejected before any DB call.
- Unknown table → rejected.
- Invalid filter op (`DELETE`) → rejected.
- Retriever runs the live query when catalog + connectors are provided.
- Sources include `"Live: orders"` alongside `"DB: revenue_metrics"`.
- No catalog → live query skipped gracefully.
- Planner returning `needed=false` → live query skipped.

### E2E with real Qwen/Qwen3.7-Plus + real SQLite
Test harness: `/app/ai-logs/e2e_live_query_test.py`.
- Q: *"Which paid customers have the highest order amounts?"*
- Qwen/Qwen3.7-Plus planner correctly picked `SELECT customer, amount FROM orders WHERE status='paid' ORDER BY amount DESC LIMIT 5`.
- SQLite driver returned 5 real rows via the safe executor (Theta $12,000 top).
- Responder cited every value inline: *"Theta: $12,000.00 (from DB: sqlite.orders)… Zeta: $3,300.00…"*
- Retriever `live_query_run=true`, `live_query_count=1`.

## Backlog / next actions
- **P0** — Extend NestJS `metrics.service.ts / chatContext(…)` to
  actually populate `catalog` + `connectors` from the user's Prisma
  `Connector` + `UnifiedDataset` rows (with secret decryption).
- **P1** — Add `run_select` support for Mongo (via `find` + projection
  whitelist) and BigQuery / Snowflake (via parameterised SQL).
- **P1** — Persist `payload.details.retriever.live_facts` in Prisma so
  the "Show reasoning" panel survives page refresh.
- **P1** — Add a per-user rate limit on live queries to prevent a
  chatty user from thrashing the source DB.
- **P2** — Column-level access control: allow the catalog to mark
  columns as `sensitive: true` so the planner is instructed to never
  request them.
- **P2** — "Explain this query" chip on the reasoning panel — clicking
  reveals the exact SQL that ran + the planner's `why` sentence.
