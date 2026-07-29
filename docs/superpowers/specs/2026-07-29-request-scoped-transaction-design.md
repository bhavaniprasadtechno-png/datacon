# Request-scoped Prisma transaction sharing

**Date:** 2026-07-29
**Status:** Approved, pending implementation plan

## Context

Real, browser-measured numbers (via `performance.getEntriesByType('resource')` against the running dev app, on the original/reverted code — see conversation history for the 3-trial trace) show clicking a conversation to messages arriving takes **~1.45-1.55s**, essentially 100% backend TTFB, near-zero frontend overhead (request fires 30-180ms after the click).

Root cause, confirmed by live query-log diagnostics against the actual Supabase/pgbouncer connection: two *independent* Postgres transactions run sequentially for what is functionally one request:

1. `SupabaseAuthGuard` (`api/src/auth/guards/supabase-auth.guard.ts`) calls `getClaims()` then `this.prisma.user.findUnique(...)` — a plain query that Prisma+pgbouncer wraps in its own `BEGIN → DEALLOCATE ALL → query → COMMIT` (~340ms, its own connection).
2. The endpoint's own `.scoped.*` call goes through `PrismaService`'s `withOrgContext` extension (`api/src/prisma/prisma.service.ts`), which opens *another*, separate `BEGIN → DEALLOCATE ALL → SET_CONFIG → query → COMMIT` (~440ms, a second connection).

`DEALLOCATE ALL` is Prisma's own defensive behavior for `pgbouncer=true` connection strings (clearing prepared statements a recycled pgbouncer backend connection might be holding) — it isn't something we can turn off, and it applies to every transaction, so it isn't optional overhead. What *is* optional is running two full transactions instead of one.

An earlier, smaller fix (cache the guard's lookup for a few seconds) was built and verified (still in `git stash`) but explicitly **not** taken here — this spec fixes the duplication at its root instead of caching around it.

**Correction made during implementation (still 2026-07-29):** the first version of this spec chose a Guard (`RequestTransactionGuard`, ordered first in the global guard chain) as the component that opens the shared transaction, specifically to get `Reflector`-based access to a `@NoRequestTransaction()` decorator. That doesn't work: a Guard's `canActivate()` just returns a boolean — Nest's own dispatcher calls the next guard/interceptor/handler *itself*, at a later point, entirely outside any code the guard controls. Resolving a promise from inside `requestTxStorage.run()` does not retroactively make that later, externally-driven code inherit the ALS context; AsyncLocalStorage only propagates to continuations of work actually *invoked* from inside `.run()`. A test proved this directly (`requestTxStorage.getStore()` came back `undefined` immediately after `canActivate()` resolved). Decisions 1 and 5 below reflect the corrected design: Express-style **middleware** instead (it gets a `next()` callback the middleware itself invokes, which is what makes the propagation actually work — the same mechanism `OrgContextInterceptor` already relies on via `next.handle().subscribe(...)`), with route exclusion via Nest's built-in `MiddlewareConsumer.exclude()` instead of a decorator, since middleware has no `Reflector` access anyway.

## Decisions

1. **One Prisma transaction per HTTP request**, opened as early as possible — in a new `RequestTransactionMiddleware` (Express-style `NestMiddleware`), registered globally in `AppModule.configure()`, which runs before guards/interceptors/handlers in Nest's pipeline and covers the auth guard's own DB work too.
2. **New `requestTxStorage`** (`AsyncLocalStorage<{ tx: Prisma.TransactionClient; rlsSet: boolean }>`), separate from the existing `orgContextStorage`. `RequestTransactionMiddleware.use(req, res, next)` kicks off `prisma.$transaction((tx) => requestTxStorage.run({ tx, rlsSet: false }, () => { next(); return <promise resolving on response finish/close>; }))` — calling `next()` itself, synchronously, from inside `.run()`'s callback is what makes the rest of the pipeline (guards, interceptors, handler) inherit the ALS context; nothing downstream needs to do anything special to see it. `orgContextStorage` is untouched — `OrgContextInterceptor` still sets it exactly as today, just now nested *inside* the already-open transaction context.
3. **`SupabaseAuthGuard`** reads `requestTxStorage`. If a request-scoped `tx` exists, it runs `tx.user.findUnique(...)` on it (no new transaction — this lookup doesn't need RLS/org-scoping, it's already keyed to the JWT-verified user id, so this is purely about reusing the connection). If none exists (excluded route), it falls back to today's `this.prisma.user.findUnique(...)`.
4. **`withOrgContext`'s `$allOperations`** checks `requestTxStorage` first. If present: run the operation directly on that `tx`, setting the RLS var only once per request (flip `rlsSet` on the shared store object — no re-`.run()`, just a mutation on the object every call in the request already reads by reference, so it reliably persists across every subsequent call in that request). If absent: unchanged, opens its own transaction exactly as today.
5. **`POST /chat/stream` and `GET /health` are excluded** via Nest's built-in `MiddlewareConsumer.exclude({ path, method })` (path-based — middleware has no `Reflector`/decorator access, so a decorator-based skip isn't an option here). `/chat/stream` keeps today's per-call-transaction behavior since the request can stream an SSE proxy response for 10s+ and holding a Postgres transaction open that long is a real resource/timeout hazard. `GET /health` is unauthenticated and hit frequently by load balancers/uptime checks — wrapping it in a transaction it doesn't need would add pointless overhead and hold a pool connection longer than necessary on a high-frequency endpoint (found during implementation, not in the original measured scope, but the same rationale applies directly).
6. **Errors propagate normally.** Anything thrown in the guard, interceptor, or handler bubbles out of the `$transaction` callback, and Prisma auto-rolls-back — identical semantics to today for mutations; irrelevant for reads.
7. **Prisma's default transaction `timeout` (5s) is left as-is.** Normal endpoints (1-3 queries) are nowhere near it; if something ever hits it, that's a signal worth surfacing loudly, not a reason to raise the ceiling pre-emptively.

## Architecture

See `app/diagram/auth-transaction-before-after/auth-transaction-before-after.svg` for the visual before/after. Text summary:

```
BEFORE (today)
Browser ──▶ SupabaseAuthGuard ──▶ OrgContextInterceptor ──▶ Service
                  │                                            │
                  ▼                                            ▼
          Transaction #1                                Transaction #2
   BEGIN→DEALLOC ALL→SELECT user→COMMIT      BEGIN→DEALLOC ALL→SET_CONFIG→SELECT→COMMIT
          ~340ms, connection A                      ~440ms, connection B
                  └──────────────┬─────────────────────┘
                                 ▼
                            PostgreSQL
                     Total: ~780ms, 2 connections, sequential

AFTER
Browser ──▶ RequestTransactionMiddleware ──▶ SupabaseAuthGuard ──▶ OrgContextInterceptor ──▶ Service
                        │                    (all four run inside the same open tx,
                        │                     because middleware calls next() itself)
                        ▼
                 Shared Transaction
     BEGIN → SELECT user → SET_CONFIG (once) → SELECT → COMMIT
                  ~350-450ms, 1 connection
                        │
                        ▼
                   PostgreSQL
        Total: ~350-450ms, 1 connection — ≈2× faster

Excluded (MiddlewareConsumer.exclude, path-based): POST /chat/stream (SSE proxy,
can run 10s+) and GET /health (unauthenticated, high-frequency) — both keep
today's per-call-transaction behavior unchanged.
```

## NestJS API changes

**New:**
- `api/src/prisma/request-transaction.storage.ts` — `requestTxStorage: AsyncLocalStorage<{ tx: Prisma.TransactionClient; rlsSet: boolean }>`.
- `api/src/prisma/request-transaction.middleware.ts` — `RequestTransactionMiddleware implements NestMiddleware`, registered in `AppModule.configure()` via `MiddlewareConsumer`, applied to all routes except `POST /chat/stream` and `GET /health` (`.exclude(...)`).

**Modified:**
- `api/src/auth/guards/supabase-auth.guard.ts` — reads `requestTxStorage`, runs its lookup on the shared `tx` when present, unchanged fallback otherwise.
- `api/src/prisma/prisma.service.ts` — `withOrgContext`'s `$allOperations` checks `requestTxStorage` before opening its own transaction.
- `api/src/app.module.ts` — implements `NestModule`, registers the middleware.

**Unchanged:** `OrgContextInterceptor`, `orgContextStorage`, every other controller/service — none of them call `.scoped.*` any differently than today.

## Error handling / edge cases

- Malformed/expired token: guard throws before resolving a user, transaction rolls back, 401 as today.
- `/chat/stream` and `/health`: no request-scoped `tx` exists (excluded), guard/service fall back to their own plain lookups — must verify these paths still work standalone.
- Tests/background code that instantiate a service directly with a mocked `PrismaService` (middleware never runs): `requestTxStorage.getStore()` is `undefined`, so `withOrgContext` falls back to opening its own transaction exactly as today — existing tests should need no changes.
- The transaction can't be opened at all (e.g. Prisma pool exhausted): `RequestTransactionMiddleware` calls `next(err)` so Nest's normal error handling takes over, rather than hanging the request.
- A slow non-streaming request approaching the 5s transaction timeout: let it fail loudly; revisit only if it happens for real.

## Testing / verification plan

1. Unit test: `RequestTransactionMiddleware` — calling `next()` from inside `.run()` makes `requestTxStorage.getStore()` visible to code that runs during and after that call; the transaction only resolves once the response finishes.
2. Unit test: `withOrgContext` uses the request-scoped `tx` when present (no new transaction opened) and falls back to opening its own when absent — covers both branches.
3. Full existing jest suite passes unmodified.
4. Re-run the exact real-number browser trace from the baseline (click conversation → `/chat/messages` via `performance.getEntriesByType('resource')`) and confirm TTFB drops from ~1.4-1.5s toward the modeled ~350-450ms.
5. Manual: `/chat/stream` still streams end-to-end and persists the conversation correctly.
6. Manual: an invalid/expired token on a non-streaming route still 401s (confirms rollback path).

## Explicitly out of scope

- The frontend refetch-storm (React Query `refetchOnWindowFocus` + Supabase auto session refresh both firing full data reloads on tab focus) — separate, unrelated fix.
- The Sidebar's global `useConversations()` call coupling every page load to chat data — separate.
- The per-transaction Postgres round-trip floor itself (`BEGIN`/`DEALLOCATE ALL`/`SET_CONFIG`/query/`COMMIT`, ~5 round trips) — this spec removes the *duplicate* transaction, not that floor.
- Prisma `connection_limit`/pool tuning — not touched.
- Reapplying the stashed guard-cache fix — superseded by this approach.
