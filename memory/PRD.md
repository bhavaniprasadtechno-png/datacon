# Datacon — PRD & Change Log

## Original problem statement
> fix the issue in chat. make the agents dynamic according to question entered by user and data
> fix the issue of chat, the shall be dynamic, system shall give accurate answers and reports based on user questions

## Architecture (unchanged)
- `web/` — React 19 + Vite chat UI (streams SSE from `api/chat/stream`)
- `api/` — NestJS controller: appends messages to Postgres via Prisma and
  proxies the SSE stream from the AI service
- `ai/` — FastAPI multi-agent orchestrator:
  **dynamic router → context filter → analytics compute → agent prep → LiteLLM streaming (or offline grounded template)**
- Data: Postgres (Prisma) for messages + metrics, ChromaDB for RAG

## Chat problems addressed
1. **Regex-only router was static.** Any phrasing outside a small keyword set
   fell through to `descriptive` or `general`.
2. **Full metrics blob was sent to every agent** regardless of question, so
   agents drowned in irrelevant data.
3. **`offline_text` was empty for every agent** — LLM failure produced blank
   chat bubbles.
4. **`predictive.payload` returned raw metrics**, breaking the forecast card.
5. **Agents just handed raw data to the LLM and hoped for accuracy** — no
   pre-computed numbers meant hallucinated percentages and vague answers.

## What was implemented (session 2 / Jan 2026)
- `ai/app/agents/router.py` — `route_dynamic(question, context, model)`: LLM
  classifier over the question + data schema; falls back to a broadened
  regex `route()` when the LLM path is unavailable.
- `ai/app/agents/context_filter.py` — narrows the metrics blob per intent
  and question; produces clean `forecast_payload` for the UI card.
- `ai/app/agents/analytics.py` (new) — real computations from context:
  `revenue_stats` (latest, MoM %, YoY %, rolling avg), `region_stats`
  (top/bottom, per-region delta vs. prior), `ticket_stats` (totals, spike
  day, first-half vs. second-half trend %), `churn_stats` (delta pp,
  direction, at-risk), and `run_forecast` which actually invokes
  Holt-Winters / OLS engines and returns projected, CI, growth %, MAPE.
- `ai/app/agents/descriptive.py` — computes revenue/region/ticket/churn
  stats, injects them into the LLM prompt as "COMPUTED FACTS" the model
  must reference; offline path is a real, numbers-cited paragraph.
- `ai/app/agents/diagnostic.py` — same, plus RAG citations; offline text
  now identifies the biggest computed driver (e.g. "ticket volume rose
  +135.3% in the 2nd half, led by NA") rather than a generic template.
- `ai/app/agents/predictive.py` — runs the REAL Holt-Winters/OLS forecast
  and hands the LLM only the resulting projected/CI/growth/MAPE facts;
  offline path reports the actual forecast; payload is the forecast object
  the UI card expects.
- `ai/app/agents/prescriptive.py` — builds a ranked action list
  deterministically from facts (retention play, support capacity, laggard
  regions, top-region playbook), each with rationale + impact_metric.
- `ai/app/internal/chat_router.py` — awaits `route_dynamic`, applies
  `filter_context` per intent before each `agent.prepare()`.

## Verified (offline unit tests in this sandbox)
- 7/7 regex router cases route correctly (single + multi-intent + off-domain).
- Per-intent context filtering: each intent gets only the relevant fields.
- Analytics compute real MoM %, YoY %, region deltas, ticket spikes, churn
  direction, and a full Holt-Winters forecast (projected/CI/growth/MAPE)
  from an 18-month synthetic series.
- All 4 domain agents produce grounded offline paragraphs citing real
  numbers (e.g. "Latest revenue: 6.20. That's +3.3% MoM. YoY +51.2%.
  Top region: NA at 2.80; weakest: LATAM at 0.30. …").
- Predictive payload now shape-matches the UI card (forecast + history +
  model + horizon), no raw metrics leaked.
- Router JSON parser tolerates markdown fences and stray prose; rejects
  invalid intents.

## What was NOT run (out of scope for this sandbox)
- Full stack boot (Postgres/Prisma migrations, ChromaDB seed, Node install,
  Vite dev server). Please boot locally / on Render with `GEMINI_API_KEY`
  set to exercise the dynamic LLM router path end-to-end.

## Backlog / next actions
- **P0** — E2E validate on a running stack with `GEMINI_API_KEY` set.
- **P1** — Cache router LLM call per (question, context_schema).
- **P1** — Extend context filter to read the user's real connected catalog
  (currently sources from the fixed NestJS `chatContext` blob).
- **P2** — Emit the router's raw JSON as a debug SSE event ("here's why
  the diagnostic + prescriptive agents were picked").
- **P2** — Move numeric formatting (currency vs. count) into a shared
  helper so units are consistent across all four agents.
