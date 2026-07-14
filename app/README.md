# Datacon

Full-stack implementation of the Datacon prototype (`../project/Datacon.dc.html`) per the PRD/SRS in `../project/uploads/`. See `/root/.claude/plans/staged-exploring-lemur.md` (or ask Claude) for the full architecture plan and phased build order.

## Stack

- `web/` — React 19 + TypeScript + Vite
- `api/` — NestJS: auth, RBAC, connector/document metadata CRUD, insights, SSE proxy
- `ai/` — FastAPI (Python): multi-agent chat, RAG (ChromaDB), forecasting, connector drivers
- `packages/prisma/` — Prisma schema/migrations + the connector-engines field registry + seed script
- `packages/shared-types/` — TS types shared between `web` and `api`

## First-time setup

Each app keeps its **own** `.env` (no shared root-level file): `api/.env`, `ai/.env`, and `packages/prisma/.env`. `DATABASE_URL` and `INTERNAL_AUTH_TOKEN` must be kept identical across the files that need them (see the comments in each `.env.example` for which siblings to match) — this is the same tradeoff `render.yaml` makes in production, where `INTERNAL_AUTH_TOKEN` is hardcoded identically into both services' env vars since Render has no cross-service variable-sharing construct.

1. **Database**: either
   - create a [Supabase](https://supabase.com) project and copy its Postgres connection string into `DATABASE_URL`, **or**
   - run Postgres locally (`docker compose up -d app_postgres`, or a native `postgresql` install) and point `DATABASE_URL` at it.
2. Copy each app's example env file and fill in secrets:
   - `cp api/.env.example api/.env` (`CONNECTOR_ENCRYPTION_KEY` — generate with `node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"`; pick an `INTERNAL_AUTH_TOKEN`)
   - `cp ai/.env.example ai/.env` (same `INTERNAL_AUTH_TOKEN` as above)
   - `cp packages/prisma/.env.example packages/prisma/.env`
3. `npm install` (installs all workspaces).
4. `npm run prisma:migrate` then `npm run prisma:seed` — seeds the exact demo dataset from the prototype (3 personas + 1 extra user, 3 system roles, 7 permissions, 4 connectors, 6 catalog tables, 5 documents). **Seed login password for every persona: `Datacon123!`**
5. `ai/`: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`, then `python3 seed_chroma.py` once to index the two seed documents the Diagnostic agent cites.
6. `npm run dev` boots `api` (port 4000), `ai` (port 8000 by default — see `AI_DEV_PORT` in `ai/.env` to change it), and `web` (port 5173) together.

For sample external data sources to test the Postgres/MySQL/MongoDB connector engines against `docker-compose.yml`'s containers, use: `postgresql://analyst:analyst@localhost:55432/analytics`, `mysql://analyst:analyst@localhost:53306/analytics`, `mongodb://analyst:analyst@localhost:57017/analytics`.

## What's implemented

- **Auth & RBAC** — double-JWT cookie auth, custom roles/permissions, Users/Roles/Assign-roles/Permissions admin pages.
- **Connectors** — all 7 engine types with real drivers (SQLite/Postgres/MySQL/HTTP fully live; MongoDB/BigQuery/Snowflake real code, need external creds/instances to exercise), AES-256-GCM secret encryption, Unified Data Store catalog with table previews.
- **Data Sources** — real upload → chunk/embed → ChromaDB indexing pipeline (PDF/TXT/MD) or column/row parsing (CSV), with the exact validation messages from the design.
- **Chat** — real intent routing, 4 agents (descriptive/diagnostic/predictive/prescriptive) computing over real seeded business data + real RAG citations, SSE token streaming, feedback.
- **Forecasts** — real OLS and Holt-Winters implementations (pure NumPy) over an 18-month revenue series, with live model/horizon controls.
- **Insights dashboard** — KPIs, anomalies, and the revenue chart all computed from the same real data, with a deep-link into Chat.
- **Themes** — 4 presets + custom accent picker, cascades via CSS custom properties, persists per-browser.

## Note on Docker-based local infra

`docker-compose.yml` defines local Postgres/MySQL/MongoDB (sample external data sources for the connector engines) and ChromaDB. In sandboxed dev environments without Docker Hub egress, install these natively instead (e.g. `apt install postgresql`) or point the relevant connector at a real hosted instance — the app itself has no hard dependency on Docker.

## LLM configuration

Chat works with **zero API keys** out of the box (deterministic offline responses computed over real retrieved/synced data). Set `GEMINI_API_KEY` to enable real LLM responses; the default model is a single `LLM_MODEL` string in `ai/.env` (default: `gemini/gemma-4-31b-it`). Gemma's `-it` models are reasoning models that spend part of their token budget on internal "thinking" before the visible answer, and have shown occasional transient errors from Google's backend — the client retries once and falls back to the offline template if both attempts fail.

Chat routes through [LiteLLM](https://docs.litellm.ai/) (per the SRS's "LLM Orchestrator" spec, `app/llm/litellm_client.py`) rather than a provider-specific SDK, so swapping providers/models is a config change, not a code change (e.g. `anthropic/claude-...` + `ANTHROPIC_API_KEY`). The chat UI also has a **per-message model picker** (top-right of the chat header) letting users switch between the curated models in `packages/shared-types/src/chat.ts`'s `AVAILABLE_LLM_MODELS` — kept in sync with `app/ai/app/llm/models.py`'s `AVAILABLE_MODELS`, which the ai service validates a per-request override against (an unrecognized model string is rejected and falls back to `LLM_MODEL` rather than being passed to LiteLLM unchecked).

**Chat streaming & multi-agent fan-out** (SRS Fig. 2): the intent classifier assigns *every* matching agent, not just the first — "why did X spike and what should we do?" fans out to diagnostic **and** prescriptive, each streaming into its own bubble with its own visualization and feedback buttons, persisted as separate messages. Tokens are streamed truly end-to-end (`litellm.acompletion(stream=True)` deltas → FastAPI SSE `agent_delta` frames → NestJS pass-through → UI), not computed-then-replayed; Gemma's thinking tokens arrive in LiteLLM's separate `reasoning_content` delta field and never leak into the visible stream. The offline (no-API-key) client reveals its deterministic text at the prototype's 3-6-chars-per-tick cadence through the same interface.

**Memory note**: importing `litellm` costs ~130MB+ RSS on first use (its `__init__` pulls in its full provider matrix regardless of which one you call), and ChromaDB's embedding model adds another 150-400MB depending on request size — comfortably fits a paid Render plan (`render.yaml` currently requests `standard`, ~2GB) but will OOM-crash on the free 512MB tier the moment a real chat/upload request lands, even though `/health` keeps passing (it never touches those code paths). If you must stay on free tier, drop back to a direct-REST client per provider instead of `litellm`, and batch ChromaDB embedding calls in small groups (both changes, and the exact memory measurements behind them, are in git history).
