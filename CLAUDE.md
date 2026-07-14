# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

This repo started life as a **Claude Design handoff bundle** (see root `README.md`): `project/Datacon.dc.html` (+ `project/screenshots/`, `chats/chat1.md`, `project/uploads/DataconPRD.docx` / `DataconSRS.docx`) is the original HTML/CSS/JS prototype and spec that `app/` is a real, full-stack implementation of. When in doubt about *intended* UX/copy/behavior, the prototype and PRD/SRS in `project/` are the source of truth — `app/README.md` explicitly says to check the PRD/SRS and the prototype before assuming.

The actual product lives entirely under **`app/`** — that's the working directory for all development.

## Stack & workspace layout (`app/`)

npm workspaces, root `app/package.json`:
- `web/` — React 19 + TypeScript + Vite frontend
- `api/` — NestJS: auth, RBAC, connector/document metadata CRUD, insights, SSE proxy to `ai`
- `ai/` — FastAPI (Python 3.11): multi-agent chat, RAG (ChromaDB), forecasting, connector drivers
- `packages/prisma/` — Prisma schema/migrations, the connector-engine field registry data, and the demo seed script
- `packages/shared-types/` — TS types shared between `web` and `api` (chat payload shapes, permissions, themes, connector engine field definitions)

`api` and `ai` are two separate backend services that only talk to each other over HTTP — `api` calls `ai`'s `/internal/*` routes (never the other way around), and `ai` is not directly reachable from the browser.

## Commands

Run from `app/`:

```bash
npm install                      # installs all workspaces
npm run dev                      # boots api (4000), ai (8000), web (5173) together via scripts/dev.sh
npm run dev:web                  # web only
npm run dev:api                  # api only (nest start --watch)
npm run dev:ai                   # ai only (uvicorn --reload)
npm run build                    # shared-types -> api -> web, in order
npm run lint                     # web (oxlint) + api (eslint)
npm run prisma:generate          # regen Prisma client
npm run prisma:migrate           # apply migrations (packages/prisma)
npm run prisma:seed              # seed demo dataset (packages/prisma/seed.ts)
```

Per-workspace, from `app/api/` or `app/web/`: `npm run start:dev` / `npm run dev`, `npm run lint`, `npm test` (api uses Jest — there are currently no `.spec.ts` test files in the repo, so `npm test` in `api/` has nothing to run yet).

AI service (`app/ai/`): `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`, then run via `npm run dev:ai` from `app/` or `uvicorn app.main:app --reload --port 8000` directly. `python3 seed_chroma.py` (once) indexes the two seed documents the Diagnostic agent cites into ChromaDB.

No standalone `ai` test suite exists either (no `test_*.py` files).

## First-time setup

1. Postgres: either a Supabase project's connection string in `DATABASE_URL`, or local Postgres (`docker compose up -d app_postgres` or a native install).
2. Each app keeps its own `.env` (no shared root-level file): `cp app/api/.env.example app/api/.env`, `cp app/ai/.env.example app/ai/.env`, `cp app/packages/prisma/.env.example app/packages/prisma/.env`. Fill in secrets — `CONNECTOR_ENCRYPTION_KEY` via `node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"`. `DATABASE_URL` must match across all three; `INTERNAL_AUTH_TOKEN` must match between `api/.env` and `ai/.env` (same shared-secret tradeoff `render.yaml` makes in production).
3. `npm install` → `npm run prisma:migrate` → `npm run prisma:seed` (seeds 3 personas + 1 extra user, 3 system roles, 7 permissions, 4 connectors, 6 catalog tables, 5 documents). **Every seeded persona logs in with password `Datacon123!`.**
4. Set up `ai/` venv (above) and run `seed_chroma.py` once.
5. `npm run dev`.

`docker-compose.yml` provides local Postgres/MySQL/MongoDB (sample connector targets) + ChromaDB for local dev; the app has no hard runtime dependency on Docker — in sandboxes without Docker Hub egress, install these natively or point connectors at real hosted instances instead.

## Architecture

### Auth & RBAC (`api/src/auth`, `users`, `roles`, `permissions`)
Double-JWT cookie auth: short-lived access token (15 min) + rotating refresh token (30 days, tracked in the `RefreshToken` table by `jti` so individual sessions can be revoked). Access token payload carries `sub`, `roleId`, and the resolved `permissions` array directly (see `auth.service.ts`), so permission checks don't need a DB round-trip per request — just `@RequirePermissions(...)` + `PermissionsGuard`. RBAC is fully custom (not a fixed enum): `Role` ↔ `Permission` is a many-to-many via `RolePermission`, editable through the Roles/Permissions admin UI. There's also a demo-only `quickLogin(personaId)` that logs straight into a seeded `isCore` user with no password, matching the prototype's persona-switcher UX.

### Connectors (`api/src/connectors`, `ai/app/connectors`, `packages/shared-types/src/connector-engines.{ts,json}`)
7 engine types (SQLite/Postgres/MySQL/MongoDB/HTTP/BigQuery/Snowflake) share one field-registry pattern: `connector-engines.json` defines each engine's connection fields (which ones are `secret`, their `kind`/`type`, labels/placeholders) once, and both the web form and the API validation derive from that single JSON. Non-secret connection details live in `Connector.config` (Json); secrets are AES-256-GCM encrypted per-field (`common/encryption.service.ts`) and stored in `Connector.secrets`, keyed off `CONNECTOR_ENCRYPTION_KEY`. Actual driver connection/sync logic (SQLite/Postgres/MySQL/HTTP are real; MongoDB/BigQuery/Snowflake have real code but need external creds to exercise) lives in `ai/app/connectors/drivers/*` — `api` owns metadata/CRUD/encryption, `ai` owns actually talking to the external system and reporting back a `UnifiedDataset` (the Unified Data Store catalog with table previews).

### Data sources / RAG (`api/src/documents`, `ai/app/rag`)
Upload → chunk → embed → ChromaDB index pipeline for PDF/TXT/MD (`ai/app/rag/chunking.py`, `chroma_store.py`), or column/row parsing for CSV. `DataSource.status` tracks the pipeline stage (`UPLOADING → CHUNKING → INDEXING → INDEXED`/`FAILED`).

### Chat / multi-agent (`api/src/chat`, `ai/app/agents`, `ai/app/llm`)
Intent routing is a **priority-ordered regex cascade** (`ai/app/agents/router.py`), ported verbatim from the original prototype (`project/Datacon.dc.html:1320-1326`) — predictive → diagnostic → prescriptive → descriptive (default) fallthrough. This is intentional per the PRD, not a stand-in for an LLM classifier — don't "improve" it into an LLM call without checking with the user first. Each of the 4 agents (`agents/descriptive.py`, `diagnostic.py`, `predictive.py`, `prescriptive.py`) computes over real seeded business data (`RevenueMetric`, `RegionRevenue`, `TicketDaily`, `ChurnSnapshot` — see Prisma schema) plus RAG citations, not canned strings.

Request flow: browser → `api` `POST /chat/stream` → `api` calls `ai` `POST /internal/chat/stream` (SSE) → `api` pipes the stream back to the browser while also buffering it to parse the terminal `event: done` payload, which it then persists as the agent `Message` once the stream ends (`chat.controller.ts`). Note the ordering in `stream()`: the AI-service call happens *before* any SSE headers are written, specifically so a failed call can still return a clean JSON 502 instead of a bare "Internal server error" (Nest can't override headers once a response has started).

LLM: works with **zero API keys** (deterministic offline fallback in `ai/app/llm/offline_client.py`, computed over real retrieved/synced data — not fake). Setting `GEMINI_API_KEY` enables real responses. `LLM_MODEL` is a single `"provider/model"` string (default `gemini/gemma-4-31b-it`) for config-level provider/model switching. **Despite the SRS specifying LiteLLM as the orchestrator**, the actual implementation (`ai/app/llm/gemini_rest_client.py`) is a direct `httpx` REST client, not the `litellm` package — importing `litellm` added +134MB RSS on first use (it eagerly loads its entire provider matrix regardless of which provider is used) and was OOM-killing the AI service on Render's free 512MB tier. `GeminiRestClient` preserves the same `LLM_MODEL` config surface (still strips a `gemini/` prefix) so swapping *models* is still just a config change; swapping to a *different provider* now requires writing an equivalent small REST client rather than a one-line config edit. Keep this in mind before "restoring" litellm.

### Internal service auth (`api` → `ai`)
`ai`'s `/internal/*` routes (connectors, documents, chat, forecast) are gated by `ai/app/internal/auth.py`'s `require_internal_auth`, which checks the `X-Internal-Auth` header against `INTERNAL_AUTH_TOKEN` — the same literal value must be set on both services. `api`'s `AiClientService` (`api/src/common/ai-client.service.ts`) is the only caller and sets a **120s timeout**, deliberately generous because Render's free tier spins the `ai` service down after ~15min idle and it can take 50s+ to cold-start.

### Forecasts (`api/src/forecasts`, `ai/app/forecasting`)
Real OLS and Holt-Winters implementations in pure NumPy (`ai/app/forecasting/ols.py`, `holt_winters.py`) over the 18-month `RevenueMetric` series — no mocked predictions.

### Insights (`api/src/insights`)
KPIs/anomalies/revenue chart computed from the same seeded metrics tables the agents use, with a deep-link into Chat.

### Frontend (`app/web/src`)
Routes under `src/routes/{auth,chat,connectors,data-sources,forecasts,insights,settings,themes}`; `src/api/*` are thin axios wrappers per domain talking to the NestJS API only (never `ai` directly); `src/auth/AuthContext.tsx` holds session/permission state; `src/theme` implements the 4 presets + custom accent picker, cascading via CSS custom properties and persisted per-browser (per `app/README.md`).

## Deployment (`render.yaml`)

Render Blueprint deploying `datacon-api` (NestJS, `rootDir: app`), `datacon-ai` (FastAPI, `rootDir: app/ai`), and a managed Postgres together. Notable non-obvious details baked into the blueprint (see inline comments in `render.yaml` for the "why"):
- `INTERNAL_AUTH_TOKEN` is a literal shared value hardcoded identically in both services' `envVars` — Render's Blueprint spec has no validated cross-service variable-sharing construct.
- `ai`'s `PYTHON_VERSION` is pinned to `3.11.15` — Render defaults to a newer Python that lacks wheels for some pinned deps.
- `ai` has no persistent disk on the free plan, so `CHROMA_PERSIST_DIR=/tmp/chroma` is ephemeral — the ChromaDB index is rebuilt from re-uploaded documents after every redeploy/restart unless upgraded to a paid plan with a `disk:` block.
- `AI_SERVICE_URL` and `CORS_ORIGINS` are `sync: false` (set manually post-deploy) since Render Blueprints can't reference another service's URL or the frontend's Vercel URL at blueprint-eval time.
