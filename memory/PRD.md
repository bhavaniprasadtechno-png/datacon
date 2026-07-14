# Datacon — PRD & Change Log

## Original problem statement
> fix the issue in chat. make the agents dynamic according to question entered by user and data
> the system shall give accurate answers and reports based on user questions
> Optionally cache the router LLM call per (question, schema) to save latency
> E2E validate on a running stack with a real GEMINI_API_KEY
> Multi-agent pipeline per system-prompt spec:
>   - Retriever: query DB via connector + uploaded documents, cite sources
>   - Analyst: interpret retrieved data
>   - Validator: cross-check DB vs uploaded data, flag conflicts/gaps
>   - Responder: compose one coherent user-facing answer
>   - Layer these around the existing analytical modes (choice 1b)
>   - Query all connected DBs (choice 2a)
>   - Show both values, flag discrepancy (choice 4b)
>   - Clean UX with expandable reasoning panel (choice 5b)

## Architecture
- `web/` — React 19 + Vite chat UI (streams SSE from `api/chat/stream`)
- `api/` — NestJS controller: appends messages to Prisma, proxies SSE
- `ai/` — FastAPI, running the multi-agent pipeline:
  **Retriever → Router (cached LLM) → Analytical modes → Validator → Responder (single streamed LLM)**
- Data: Postgres (Prisma) for messages + metrics, ChromaDB for RAG

## Multi-agent pipeline (this session)
Every chat turn now flows through 4 pipeline stages layered around the 4
analytical modes:

1. **Retriever** (`agents/retriever.py`, deterministic) — tags every field
   in the incoming NestJS `chatContext` blob with its origin DB table
   (`revenue_metrics`, `region_revenue`, `ticket_daily`, `churn_snapshot`,
   `data_sources`), retrieves the top-k relevant document chunks from
   ChromaDB, and returns a bundle of `{db_facts, doc_facts, sources,
   coverage}`. Sources are emitted as chips on the responder message.

2. **Router** (`agents/router.py`, cached LLM) — LLM-driven intent
   classifier that picks which analytical modes are relevant to the
   question. Broadened regex router remains as offline fallback.
   Results cached per `(question_lower, data-schema, model)` in a bounded
   LRU+TTL cache (512 entries, 15 min).

3. **Analytical modes** (`agents/{descriptive,diagnostic,predictive,
   prescriptive,general}.py`, deterministic) — each computes its own
   analytics via `agents/analytics.py` and produces a structured payload:
   revenue stats, region deltas, ticket spike/trend, churn direction, or a
   REAL Holt-Winters/OLS forecast. **No per-analyst LLM call anymore** —
   the responder consumes the deterministic payloads.

4. **Validator** (`agents/validator.py`, deterministic) — cross-checks
   numbers appearing in both DB facts and document snippets. Emits
   `{conflicts, gaps, freshness_notes}`. Conflicts fire when a DB number
   and a doc-snippet number are numerically close but differ > 5%. Gaps
   fire when the question implies data that wasn't retrieved
   (e.g. "forecast" but no `revenueHistory`).

5. **Responder** (`agents/responder.py`, single streamed LLM) — composes
   ONE coherent answer citing sources inline
   (`(from DB: revenue_metrics)`, `(from Doc: Q3.pdf)`), surfaces both
   values when the validator flagged a conflict, says "no matching data"
   when the validator flagged a gap. Ends every answer with a
   `Sources:` line. Deterministic offline fallback template is
   activated when the LLM is unavailable — still cites sources,
   still surfaces conflicts/gaps.

Small-talk / off-domain path (`intents == ["general"]`) bypasses the
analytics responder and uses the general agent's conversational reply
directly.

## SSE contract (unchanged for the frontend's happy path)
- `retriever_done` — sources, coverage counts, coverage list.
- `validator_done` — conflicts + gaps + freshness notes.
- `agents` — `[primary_intent]` (single visible bubble).
- `agent_delta` — responder tokens streamed live.
- `agent_done` — full pipeline breakdown in `payload.details` for the
  frontend's expandable reasoning panel.
- `done`.

## Frontend
- `web/src/routes/chat/AgentVisualization.tsx` — new
  `PipelineDetailsPanel` renders:
  * Source chips (DB tables + doc titles) always visible.
  * Conflict / gap warning cards always visible when the validator
    flagged something.
  * Collapsible "▸ Show reasoning" toggle reveals: analyst modes
    invoked, database fields retrieved, and document snippets.
- Existing inline visualizations (bar chart / forecast card / actions
  table / citations) preserved for backward compat.
- Frontend TS type-check passes (`tsc --noEmit -p .`).

## Verified this session
### Unit tests (offline, deterministic)
- Retriever tags DB fields with `source` labels; correctly identifies
  present/missing fields for `coverage`.
- Validator flags a genuine 4.8 vs 5.5 churn conflict (>5% delta),
  ignores unrelated numbers.
- Validator flags gap when "forecast" question hits an empty
  `revenueHistory`.
- Responder offline path cites sources inline and surfaces
  conflicts/gaps.

### E2E (against live FastAPI ai/ + real Gemini API key)
Test harness `/app/ai-logs/e2e_pipeline_test.py`.

| Scenario | Latency | Path | Behavior |
|---|---|---|---|
| Warmup "hello there" | 2.8–4s | Gemini | Friendly conversational reply |
| Descriptive | 6.1s | Gemini | *"Total revenue reached 6.2, marking a 3.33% increase MoM and a significant 51.22% increase YoY (from DB: revenue_metrics). Regionally, NA leads with 2.8 (from DB: region_revenue)... Customer churn is currently at 4.8%..."* |
| Multi (diagnostic+prescriptive) | 6.5s | Gemini | Multi-agent dynamic routing verified; source citation everywhere |
| Predictive | 9.4s | Gemini | Holt-Winters output cited (proj 7.2, CI 6.6–7.81, MAPE 2.41%) |
| Cache hit repeat | 0.14–0.16s | Cache | ~45× speedup on the router LLM call |

Rate-limit fallback (free-tier 5 RPM) also validated — responder falls
back to its deterministic template which STILL cites sources.

## Bugs found & fixed this session
1. `GEMINI_API_KEY` was in pydantic settings but never bridged to
   `os.environ` where LiteLLM reads it — silently fell back to offline
   templates. Fixed in `config.py`.
2. `max_tokens=1024` truncated Gemini 2.5 Flash to ~20 visible tokens
   (model spent ~1000 tokens on internal reasoning first). Bumped to
   `max_tokens=3072`.
3. General intent was dumping business data on greetings. Bypassed
   responder for `intents == ["general"]`.

## Backlog / next actions
- **P0** — Full stack boot (Postgres + Prisma migrate/seed + Nest +
  Vite) + Playwright click-through in the actual UI. Recommend a paid
  Gemini quota tier so multi-agent fan-outs don't rate-limit.
- **P1** — Extend the retriever to run LIVE queries against connectors
  when the question requires data not in the pre-computed metrics blob
  (currently only tags the pre-loaded Prisma-derived fields).
- **P1** — Add XLSX/DOCX/JSON parsers to the document upload path.
- **P1** — Persist `payload.details` alongside the responder message
  in Prisma so the "Show reasoning" panel survives page refresh
  (currently detail lives only in the streamed SSE frame).
- **P2** — Preload `litellm` at process start (~130MB import cost on
  first request).
- **P2** — "Export report" — download the responder answer + details
  as PDF/Markdown briefing.
