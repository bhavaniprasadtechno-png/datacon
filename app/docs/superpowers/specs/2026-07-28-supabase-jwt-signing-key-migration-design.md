# Supabase JWT Signing Key Migration — Design

## Problem

Every API call through the NestJS API (`/documents`, `/users`, `/roles`, `/connectors`, `/catalog`, and every other route behind `SupabaseAuthGuard`) takes ~1.1-1.2s, uniformly, regardless of what the endpoint actually does.

## Root Cause

`SupabaseAuthGuard` (`api/src/auth/guards/supabase-auth.guard.ts:12-42`) is applied via `@UseGuards(SupabaseAuthGuard, PermissionsGuard)` on every controller, so it runs on every guarded request. Its `canActivate()` calls:

```ts
const { data, error } = await getSupabaseAdminClient().auth.getClaims(token);
```

Per `supabase-js`'s own source (verified via Context7, not training-data assumption): for **HS256** (symmetric) tokens, `getClaims()` cannot verify the signature locally — a symmetric secret can't be safely published as a JWKS for others to check against — so it silently falls back to `getUser(token)`, a real network round-trip to Supabase's Auth server (GoTrue).

The project `datacon-staging-ew` (ref `yicblouwgguhmfvwqdhm`, region `ap-southeast-1`, confirmed via `mcp__supabase-2__list_projects`) currently uses the legacy shared HS256 JWT secret. That network hop, repeated on every single request, is the entire observed latency — traced and confirmed the Prisma lookup, `PermissionsGuard` (in-memory only), and each endpoint's own query are all fast.

## Frontend/Backend Boundary (explicit requirement)

Confirmed by reading `web/src/api/client.ts:8-14`: the frontend performs **zero** auth logic. It reads the already-issued session token via `supabase.auth.getSession()` (a local read, no verification) and attaches it as `Authorization: Bearer <token>`. All verification, the Prisma user/role/permission lookup, and suspension checks live entirely in `api/src/auth/guards/supabase-auth.guard.ts`, server-side. This design changes nothing about that boundary — the fix is a Supabase project configuration change, not a code change, and the local-verification step (`getClaims()` using Web Crypto) still executes inside the same server-side guard, using Node's built-in `crypto.subtle`, never the browser.

## Approaches Considered

**A — Migrate to asymmetric ES256 signing key (chosen).** Supabase Dashboard: Migrate → create ES256 standby key → Rotate → Revoke old key (after a wait window). Zero application code changes — `getClaims()` already auto-detects the token's `alg` header and switches to local Web Crypto verification with cached JWKS once tokens carry ES256. This is Supabase's own documented, vendor-intended fix path.

**B — Verify JWT locally in code (HS256), bypassing `getClaims()`.** Rewrite the guard to verify with `jsonwebtoken` + `SUPABASE_JWT_SECRET` directly. Rejected: duplicates verification logic the SDK already owns, drifts if Supabase changes token format internals, and buys nothing Approach A doesn't already give for free (the guard's own Prisma-based suspension check already covers what `getUser()`'s server round-trip would additionally catch).

**C — Cache verified claims in-memory for N seconds.** Memoize `getClaims()` per token in the guard. Rejected: band-aid, not a fix — cold cache (first request, pod restart, new replica) is still slow, and it doesn't work correctly across multiple API replicas without shared state (Redis), which is more infrastructure than Approach A needs.

## Design

### Data flow (after fix)

Browser attaches the same Bearer token as always (unchanged) → `SupabaseAuthGuard.canActivate()` → `getClaims()` verifies **locally** (no network hop) → Prisma lookup for user/role/permissions/org status (unchanged) → `PermissionsGuard` (unchanged, in-memory, no I/O) → controller → service (unchanged). Only the token-verification step's internal mechanism changes; every other step in the request path is byte-for-byte identical to today.

### Components touched

- Supabase project JWT Keys (Dashboard-managed configuration) — the only thing that actually changes.
- `api/src/auth/guards/supabase-auth.guard.ts` — reference point only, zero edits.
- `web/src/api/client.ts` — reference point only, confirms frontend stays untouched, zero edits.

### Migration mechanics (Supabase's documented key lifecycle)

1. **Migrate** — Dashboard → Settings → API → JWT Keys → "Migrate JWT secret". Imports the existing HS256 secret into the new keys system. No behavior change.
2. **Create standby key** — new key, algorithm ES256, state Standby (generated, unused).
3. **Rotate** — promotes ES256 to **In Use**; old HS256 key automatically moves to **Previously Used** (keeps validating any already-issued, unexpired tokens — no forced sign-outs).
4. **Wait** ≥ access-token TTL + buffer (e.g. ≥1h15m if TTL=1h) — the safety window before it's safe to revoke.
5. **Revoke** — old HS256 key → Revoked. **Gated behind explicit user go-ahead**, not a timer, since it's the one irreversible step (short of permanent key deletion).

### Error handling / rollback

Every key state is reversible except permanent deletion (Supabase docs, confirmed via `search_docs`/Context7). If anything breaks after Rotate (step 3) but before Revoke (step 5): move the ES256 key back to Standby, rotate again — this promotes the old HS256 key (still "Previously Used") back to "In Use," instantly restoring pre-migration behavior while the ES256 issue is investigated. This rollback path only exists before the Revoke step, which is exactly why Revoke is gated on explicit confirmation rather than automated.

### Verification

- Decode a freshly-issued access token header, confirm `"alg":"ES256"`.
- `curl -w "%{time_total}\n"` timing on `/documents`, `/users`, `/roles`, `/connectors`, `/catalog` before/after — expect ~1.1-1.2s → double-digit ms.
- Spot-check `/forecasts`, `/insights`, `/chat` (same guard pattern) for regressions.

## Execution constraints (confirmed with user)

- No code changes — migration only, not a `SupabaseAuthGuard`/`CurrentUserGuard` split.
- Dashboard steps (Migrate/Create/Rotate/Revoke) are performed by the user, not automated — no Supabase CLI or MCP tool covers this (checked `supabase --help`, `supabase gen --help`, `supabase projects --help`).
- Revoke requires an explicit user go-ahead after the wait window — never automatic.
