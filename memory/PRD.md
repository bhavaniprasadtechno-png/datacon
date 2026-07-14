# Datacon — PRD & Change Log

## Original problem statement
> fix the issue in chat. make the agents dynamic according to question entered by user and data

## Architecture (existing, unchanged)
- `web/` — React 19 + Vite chat UI (streams SSE from `api/chat/stream`)
- `api/` — NestJS controller that appends messages to Postgres via Prisma and
  proxies the SSE stream from the AI service
- `ai/` — FastAPI multi-agent orchestrator: router → per-intent agent prep →
  LiteLLM streaming (or offline template fallback)
- Data: Postgres (Prisma) for messages + business metrics, ChromaDB for RAG

## Chat issues fixed in this session (Jan 2026)
1. **Regex-only router was static.** Anything phrased outside a small keyword
   set fell through to `descriptive` or `general`.
2. **Full metrics blob was pushed to every agent** — revenue, tickets,
   churn, regions, incidents all sent regardless of what was asked.
3. **`offline_text` was empty for every agent**, so when Gemini was
   unreachable / not configured, chat bubbles rendered blank.
4. **`predictive.payload` returned the raw metrics blob**, breaking the
   frontend forecast card.

## What was implemented
- `ai/app/agents/router.py` — added `route_dynamic(question, context, model)`,
  an LLM-driven classifier that reads the question + a compact schema of the
  data attached to the turn and returns which agents run. Deterministic
  regex `route()` retained (broadened) as fallback when
  `GEMINI_API_KEY` is unset, the LLM call fails, or the reply is unparseable.
- `ai/app/agents/context_filter.py` — new. `filter_context()` narrows the
  metrics blob to fields relevant to (intent × question). `forecast_payload()`
  gives predictive a clean, forecast-shaped payload.
- `ai/app/agents/{descriptive,diagnostic,predictive,prescriptive,general}.py`
  — each now returns a deterministic, data-driven `offline_text` so chat
  bubbles are never blank when the LLM fails.
- `ai/app/internal/chat_router.py` — now `await route_dynamic(...)` and
  applies `filter_context(...)` per intent before calling `agent.prepare()`.

## Verified (offline unit tests)
- All 7 router keyword cases route to the expected agent(s).
- Per-intent context filtering drops irrelevant fields; `general` gets nothing.
- Offline text is non-empty and cites real numbers for every agent.
- LLM router JSON parser tolerates markdown fences and surrounding prose,
  rejects invalid intents.
- `route_dynamic` falls back to regex when `GEMINI_API_KEY` is absent
  (verified in this sandbox).

## What was NOT run (out of scope for this sandbox)
- Full stack boot (Postgres/Prisma migrations, ChromaDB seed, Node install,
  Vite dev server) — the repo is a design/handoff bundle without a
  supervisor-managed running service here.

## Backlog / next actions
- **P0** — validate end-to-end in a real environment once the stack is
  booted (Postgres + `npm run dev` + `GEMINI_API_KEY`).
- **P1** — cache the router LLM call per (question, context_schema) to
  avoid an extra round-trip on every turn.
- **P1** — teach the router to bias intent choice by which datasets the
  user has actually connected (currently reads the fixed metrics blob
  shipped by NestJS; extending to real Prisma-derived catalog is a small
  step from here).
- **P2** — expose a `debug=1` flag on `/internal/chat/stream` that emits
  the router's raw JSON alongside the `agents` event, for observability.
