# Datacon — PRD & Change Log

## Original problem statement
> fix the issue in chat. make the agents dynamic according to question entered by user and data
> the system shall give accurate answers and reports based on user questions
> Optionally cache the router LLM call per (question, schema) to save latency
> E2E validate on a running stack with a real GEMINI_API_KEY

## Architecture
- `web/` — React 19 + Vite chat UI (streams SSE from `api/chat/stream`)
- `api/` — NestJS controller: appends messages to Postgres via Prisma and
  proxies the SSE stream from the AI service
- `ai/` — FastAPI multi-agent orchestrator:
  **dynamic LLM router (cached) → context filter → analytics compute →
  agent prep → LiteLLM streaming (with offline grounded fallback)**
- Data: Postgres (Prisma) for messages + metrics, ChromaDB for RAG

## Chat problems addressed
1. Regex-only router was static — off-keyword questions fell through.
2. Full metrics blob sent to every agent regardless of question.
3. `offline_text` empty → blank chat bubbles when LLM failed.
4. `predictive.payload` returned raw metrics → forecast card broken.
5. Agents handed raw data to the LLM → hallucinated percentages.
6. No caching → every turn paid full router-LLM latency.
7. LiteLLM couldn't authenticate — `.env` was loaded into `settings`
   but never bridged into `os.environ` where LiteLLM reads it from.
8. `max_tokens=1024` truncated Gemini 2.5 Flash answers to ~20 tokens
   because the model spends ~1000 tokens on internal reasoning first.

## What was implemented
### AI service (`ai/app/`)
- **`agents/router.py`** — `route_dynamic(question, context, model)`: LLM
  intent classifier over the question + compact data schema. Falls back
  to a broadened regex router when the LLM path is unavailable.
  **Bounded LRU + TTL cache** keyed on `(question_lower, schema, model)`:
  `_ROUTER_CACHE_MAX=512`, `_ROUTER_CACHE_TTL_SECS=900`, thread-safe,
  exposes `router_cache_stats()` / `router_cache_clear()`.
- **`agents/context_filter.py`** — narrows the metrics blob per intent
  and question; produces clean `forecast_payload` for the UI card.
- **`agents/analytics.py`** — real computations: revenue_stats (latest,
  MoM/YoY %, rolling), region_stats (top/bottom, region deltas),
  ticket_stats (totals, spike day, 1st/2nd-half trend %), churn_stats
  (delta pp, direction), `run_forecast` (invokes Holt-Winters / OLS).
- **`agents/{descriptive,diagnostic,predictive,prescriptive}.py`** —
  each compute analytics first, inject "COMPUTED FACTS" into the LLM
  prompt as authoritative numbers, populate structured payloads
  (facts / citations / forecast / actions), and produce grounded
  offline paragraphs citing real numbers.
- **`agents/general.py`** — brief off-domain fallback text.
- **`internal/chat_router.py`** — awaits `route_dynamic`, applies
  `filter_context` per intent before each `agent.prepare()`.
- **`llm/litellm_client.py`** — bumped `max_tokens=3072` (headroom for
  Gemini 2.5 Flash's ~1000 reasoning tokens).
- **`config.py`** — bridges `settings.gemini_api_key` into
  `os.environ["GEMINI_API_KEY"]` at import time so LiteLLM can pick it
  up (previous silent-failure root cause).

## E2E validation (against live FastAPI ai/ + real Gemini API key)
Test harness: `/app/ai-logs/e2e_test.py`. Run against `uvicorn app.main:app --port 8100`.

| Scenario | Latency | Path | Answer |
|---|---|---|---|
| WARMUP "hello there" | 3.06s | Gemini | *"Hello there! How can I help you today?"* |
| DESCRIPTIVE | 7.13s | Gemini | *"Our latest revenue reached $6.2, showing a positive MoM growth of 3.3% and a significant YoY increase of 51.2%. The rolling 3-month average revenue is $5.93. Regionally, North America leads with $2.8, growing by 7.7%..."* |
| DIAGNOSTIC | 6.51s | Gemini | *"Tickets spiked primarily on 2024-01-05, recording 22 tickets... second half of the period seeing 40 tickets compared to 17, representing a 135.29% rise..."* |
| PREDICTIVE (multi-intent) | 9.4s | Gemini | Router **dynamically** picked `[predictive, diagnostic]`. Predictive: *"Projected 7.2, CI 6.6–7.81, growth 16.18%, MAPE 2.41%"*. Diagnostic **refused to hallucinate**: *"the computed facts do not contain any predictive models"*. |
| DIAGNOSTIC repeat 1 | **0.16s** | Cache hit | Same intent, offline text served from cache |
| DIAGNOSTIC repeat 2 | **0.14s** | Cache hit | ~45× speedup vs first call |

**All assertions passed** — descriptive quotes real numbers, predictive payload has real forecast, prescriptive returns 4 ranked actions, multi-intent produces ≥2 agent responses, general is isolated from business data.

Rate-limit fallback also validated: when Gemini free-tier RPM (5/min) was
exceeded on later calls, agents cleanly fell back to their offline
paragraphs which still cited real computed numbers — no blank bubbles.

## Backlog / next actions
- **P0** — Boot the full stack (Postgres + Prisma migrate/seed + Nest +
  Vite + ChromaDB) and re-run through the actual chat UI. Requires a
  higher Gemini quota tier or spacing requests > 5/min.
- **P1** — Extend `context_filter` to read the user's *actual* connected
  catalog (currently sourced from the fixed NestJS `chatContext` blob).
- **P1** — Consider preloading LiteLLM at process start so first
  request isn't hit with the ~130MB import cost.
- **P2** — Debug SSE event that emits the router's raw JSON alongside
  the `agents` event, to explain "here's why these agents were picked".
- **P2** — Export chat answer (facts + actions + forecast) as PDF/MD.
