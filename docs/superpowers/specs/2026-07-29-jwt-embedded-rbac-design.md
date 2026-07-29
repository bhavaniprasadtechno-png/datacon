# JWT-embedded RBAC + minimal live suspension check

**Date:** 2026-07-29
**Status:** Approved, pending implementation plan

## Context

Live query-log tracing (`prisma.$on('query', ...)`, same technique used for the earlier transaction-sharing fix) proved `SupabaseAuthGuard`'s `user.findUnique({ include: { role: { include: { permissions: true } }, org: {...} } })` is **not** one query — Prisma splits it into 4 sequential round trips, one per relation level:

```
SELECT users            (1 row)    ~103ms
SELECT roles             (1 row)    ~100ms
SELECT role_permissions  (7 rows)   ~100ms
SELECT organizations     (1 row)    ~100ms
```

≈400ms total, matching the guard's measured ~405-430ms exactly (confirmed by two independent live traces on the running app). This is on top of the request-scoped-transaction work already shipped (`docs/superpowers/specs/2026-07-29-request-scoped-transaction-design.md`), which removed the *duplicate*-transaction cost but not this per-relation round-trip cost.

This query does two genuinely different jobs:
- **RBAC** (`orgId`, `roleId`, `permissions`) — authorization data, changes rarely.
- **Suspension status** (`user.status`, `org.status`) — must be enforced on the very next request, cannot tolerate staleness.

## Decisions

1. **RBAC moves into the JWT** via a Supabase Custom Access Token Hook — a Postgres function, run by Supabase Auth at token mint (login) and refresh, that injects `app_org_id`, `app_role_id`, `app_permissions` into the token's claims. `SupabaseAuthGuard` reads these directly from `getClaims()`'s already-decoded output — zero extra round trips, since `getClaims()` is already called for identity verification.
2. **Suspension check stays a live DB query, every request, no exceptions** — but shrinks to one flat query: `user.findUnique({ where: { id }, select: { status: true, org: { select: { status: true } } } })`. `org` here is a to-one relation, which Prisma joins into a single SQL statement (confirmed: this exact shape, before the `role`/`permissions` include was added, produced one query in the trace) — one round trip, ~100ms, not four.
3. **No fallback for tokens minted before the hook exists.** If `app_org_id`/`app_role_id`/`app_permissions` are missing from the claims, the guard throws `UnauthorizedException` — same as an invalid token. This is a deliberate choice (confirmed with the user): every currently-active session gets force-logged-out the moment this ships, rather than silently degrading to today's slow path until each token's next natural refresh. Trades a one-time, all-at-once "please sign in again" for zero fallback-code-path complexity and no ambiguity about which sessions are on which behavior.
4. **Role/permission changes take effect on next token refresh** (Supabase's access-token TTL — 3600s per the project's current setting, confirmed from a live token's `expires_in`), same tradeoff already accepted for the earlier JWT-signing-key work. **Suspension is unaffected by this tradeoff** — it's still a live check on every single request, same as today.
5. This applies to `SupabaseAuthGuard` only. `PlatformAdminGuard` (separate identity space, no RBAC — just a boolean "is this a platform admin") and `SupabaseTokenGuard` (no DB lookup at all, used only by the two bootstrapping routes) are untouched.

## Architecture

```
BEFORE (after the transaction-sharing fix, before this spec)
getClaims() [~2ms, local ES256 verify]
  → user.findUnique({ include: { role: { include: { permissions }}, org }})
      = 4 sequential round trips: users → roles → role_permissions → organizations
      ≈ 400ms

AFTER
getClaims() [~2ms] → claims already contain app_org_id / app_role_id / app_permissions
  → user.findUnique({ select: { status, org: { select: { status }}}})
      = 1 round trip (to-one relation, single JOIN)
      ≈ 100ms

Guard's DB cost: ~400ms → ~100ms. getClaims() itself unaffected (already fixed separately).
```

## Components touched

**New (Supabase project config, not app code):**
- `custom_access_token_hook(event jsonb) returns jsonb` — Postgres function (migration), reads `users`/`role_permissions` for `event->>'user_id'`, injects `app_org_id`/`app_role_id`/`app_permissions` into `event->'claims'`.
- Enabling the hook: Supabase Dashboard → Authentication → Hooks → select the function. **Dashboard-only step** — no Supabase CLI/MCP tool covers hook *enablement* (the function itself can be created via `mcp__supabase-2__apply_migration`, but wiring it into Auth's hook config cannot, confirmed against the same tool limitations documented in the JWT-signing-key migration plan).

**Modified:**
- `api/src/auth/guards/supabase-auth.guard.ts` — reads `app_org_id`/`app_role_id`/`app_permissions` from `getClaims()`'s output; throws `UnauthorizedException` if any are missing; suspension check query narrowed to the flat `select` shape above.
- `api/src/auth/guards/supabase-auth.guard.spec.ts` — rewritten for the new claims-based shape (mocks `getClaims()` returning the new claims instead of mocking `user.findUnique` for RBAC data; keeps a mocked `user.findUnique` for the narrower suspension-only query).

**Unchanged:** `PlatformAdminGuard`, `SupabaseTokenGuard`, `AuthService.me()` (separate code path, not touched by this spec), `PrismaService`/`requestTxStorage` (this spec doesn't change how the shared transaction is used, just what's queried within it), `PermissionsGuard` (still reads `req.user.permissions`, doesn't care where that array came from).

## Error handling / edge cases

- Token missing the new claims (pre-hook token, or hook misconfigured): `UnauthorizedException`, forces re-login — this is Decision 3, not a bug.
- User suspended mid-session: caught on their very next request, same as today — unaffected by this change.
- Org suspended mid-session: same — unaffected.
- Role reassigned or a role's permissions edited: doesn't take effect until the user's token next refreshes (up to ~1hr) — an accepted, explicit tradeoff (Decision 4), not silently different from what's communicated to the user.
- Hook function query returns no matching user (e.g., a Supabase Auth user with no `users` row yet — shouldn't happen for `SupabaseAuthGuard`-protected routes, which require a completed profile, but the hook must not error in that case): hook returns the event with claims unmodified (no `app_org_id`/etc. added) rather than throwing — the guard's existing "missing claims → Unauthorized" path handles it correctly without the hook needing special-case logic.

## Testing / verification plan

1. Unit test: guard reads `orgId`/`roleId`/`permissions` from claims, does not call `user.findUnique` for that data.
2. Unit test: guard throws `UnauthorizedException` when `app_org_id`/`app_role_id`/`app_permissions` are absent from claims.
3. Unit test: guard's suspension check still throws `ForbiddenException` for a suspended user or suspended org, using the new narrower query shape.
4. Full existing jest suite passes (with the guard spec file's RBAC-related tests rewritten per Decision 3 — this is an intentional, expected test change, not a regression).
5. Manual, against the real running app: confirm the hook is live (decode a freshly-minted token, confirm `app_org_id`/`app_role_id`/`app_permissions` present), confirm a stale pre-hook token is rejected (forces re-login), re-run the same real-browser click-to-data trace used throughout this session and confirm the guard's DB portion drops from ~400ms toward ~100ms.
6. Manual: suspend a test user via the platform-admin UI mid-session, confirm their very next request is blocked immediately (not after any delay) — this is the one guarantee that must not regress.

## Explicitly out of scope

- `AuthService.me()` / `/auth/me` — separate code path (uses `SupabaseTokenGuard`, checks `PlatformAdmin` first), still has the original pre-this-session nested-transaction issue sitting in `git stash`, not touched here.
- Reducing the suspension check below one round trip (e.g., caching suspension status) — rejected earlier in this session for the same reason Approach C was rejected in the JWT-signing-key design: a stale cache is exactly the failure mode suspension enforcement can't tolerate.
- Any change to `PlatformAdminGuard` or the platform-admin route tree.
- Shortening Supabase's access-token TTL to reduce the RBAC staleness window — not requested, would increase refresh frequency for no benefit to the suspension guarantee this spec cares most about.
