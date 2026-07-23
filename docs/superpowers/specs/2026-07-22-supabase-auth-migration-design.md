# Supabase migration: database + authentication

**Date:** 2026-07-22
**Status:** Approved, pending implementation plan

## Context

Datacon currently runs its own primary Postgres in Docker (`app_postgres` in
`docker-compose.yml`) and implements auth from scratch in the NestJS API:
bcrypt password hashes, hand-rolled access/refresh JWT pairs, a
`RefreshToken` table for rotation, and httpOnly cookies. The RBAC layer
(`User → Role → Permission`) is a real product feature (roles/permissions
management UI exists under Settings) independent of how identity is
verified.

The `docker-compose.yml` file already documents the intent to move the
app's primary database to Supabase Postgres in real deployments — this spec
executes that, and additionally replaces the custom JWT system with
Supabase Auth. A staging Supabase project, `datacon-staging-ew`
(`yicblouwgguhmfvwqdhm`, ap-southeast-1, Postgres 17), already exists and is
currently empty, so this is a schema-first migration with no data backfill.

Note: `ConnectorEngine.SUPABASE` (in `packages/prisma/schema.prisma`) is an
unrelated feature — it lets *customers* connect their own Supabase project
as a data source. It is not touched by this migration.

Also out of scope: `app/ai`'s `require_internal_auth` — a static shared
secret between NestJS and the FastAPI service, unrelated to user-facing
auth.

## Decisions

1. **Auth pattern:** Bearer token via `supabase-js`. The web app
   authenticates directly against Supabase Auth (sign-in/sign-up/sign-out,
   session refresh — all handled by `supabase-js`). It sends the Supabase
   access token as `Authorization: Bearer <token>` to the NestJS API, which
   verifies it locally via `supabase.auth.getClaims()` (JWKS-based, no
   Supabase Auth server round-trip per request, and forward-compatible with
   Supabase's asymmetric signing-key rotation).
2. **RBAC:** stays exactly as-is — `Role`/`Permission`/`RolePermission`
   tables live in the same Supabase Postgres, now keyed by the Supabase
   user's UUID instead of a locally generated cuid. Guards
   (`PermissionsGuard`) and decorators (`RequirePermissions`,
   `RequireAnyPermission`, `CurrentUser`) are unchanged; only where the
   verified user id comes from changes.
3. **Quick-login demo personas:** recreated as real Supabase Auth users
   sharing the existing documented seed password (`Datacon123!`). The
   "quick login" button becomes a direct `signInWithPassword(email,
   SEED_PASSWORD)` call — no custom admin/session-minting code.
4. **Sequencing:** DB hosting and auth migrate together in one spec/plan,
   since the `users` table needs to live in the same Postgres as
   `auth.users` regardless.

## Architecture

```
Browser (web/)                    NestJS API (api/)              Supabase
─────────────────                 ──────────────────             ──────────
supabase-js  ──sign in/up/out──►  (nothing — direct call)  ──►  Auth (GoTrue)
     │                                                             │
     ├─ session (access token, auto-refreshed by supabase-js)      │
     │                                                             │
     └─ axios ──Bearer <token>──►  SupabaseAuthGuard                │
                                     .getClaims(token) ─────────────┘
                                     (JWKS verify, local, cached)
                                          │
                                     req.user = { id, email }
                                          │
                                     PermissionsGuard / CurrentUser
                                          │
                                     Prisma → Postgres (same DB Supabase Auth uses)
                                     Role / Permission / RolePermission / users
```

Prisma keeps using a privileged Postgres connection string (not the Supabase
anon/authenticated client), same trust model as today. Supabase auto-exposes
every `public` schema table via its PostgREST REST API to the
anon/authenticated roles, independent of how Prisma connects — since the app
has no browser-side Postgres access path (the web app only uses supabase-js
for Auth, never for direct table access), every `public` table gets RLS
enabled with zero policies, which blocks the anon/authenticated REST API
outright while leaving Prisma's privileged connection unaffected (the
`postgres` role bypasses RLS). This was corrected mid-implementation after
Supabase's own migration tooling flagged RLS-disabled tables as a critical
exposure — see
`packages/prisma/migrations/20260722080000_supabase_auth/migration.sql`.

## Schema changes (`packages/prisma/schema.prisma`)

- `User.id`: `String @id @default(cuid())` → `String @id @db.Uuid`, no
  default. The id always comes from Supabase (assigned at signup or at
  admin-invite time), never generated locally.
- Drop `User.passwordHash` and `User.tokenVersion`.
- Delete the `RefreshToken` model entirely (Supabase owns session/refresh
  lifecycle).
- No cross-schema FK from `public.users.id` to `auth.users.id`. Skipped
  deliberately: the app always creates the local profile row in the same
  flow that creates the Supabase auth user (signup trigger, or admin invite
  followed immediately by a local insert), so orphan rows aren't expected.
  Add the FK later only if drift is actually observed in practice.
- New Postgres trigger `on_auth_user_created` → `handle_new_user()` on
  `auth.users`: inserts a `public.users` row with the default `viewer` role
  whenever a user signs up directly through `supabase-js`. This replaces
  `AuthService.register()`'s current logic (hash password, insert user).

## NestJS API changes (`app/api/src/auth/**`, `app/api/src/users/**`)

**Delete:**
- `strategies/jwt.strategy.ts`, `strategies/jwt-refresh.strategy.ts`
- `guards/jwt-auth.guard.ts`, `guards/jwt-refresh.guard.ts`
- Token-issuing logic in `auth.service.ts` (`issueTokens`, `register`,
  `login`, `refresh`, `logout`, the `RefreshToken` bookkeeping)
- `dto/login.dto.ts`, `dto/register.dto.ts`
- Routes: `POST /auth/login`, `POST /auth/register`, `POST /auth/refresh`,
  `POST /auth/logout` — all superseded by direct `supabase-js` calls from
  the browser.

**Add:**
- `SupabaseAuthGuard`: reads `Authorization: Bearer`, calls
  `getClaims(token)` against a server-side Supabase client constructed with
  the service-role key (never sent to the browser), attaches
  `{ id, email }` to `req.user` on success, 401s otherwise.

**Keep, adjusted:**
- `GET /auth/me`: verify token → join local `Role`/`Permission` by the
  verified user id → return profile + permissions (logic mostly unchanged,
  just no longer reads `passwordHash`/`tokenVersion`).
- `GET /auth/personas`: unchanged, still backs the quick-login roster UI.
- `PermissionsGuard`, `CurrentUser`, `RequirePermissions`,
  `RequireAnyPermission`: unchanged.
- `users.service.ts` `create()`: replace the current
  `bcrypt.hash(randomSalt)` placeholder (already flagged in-code as a
  temporary stub) with `supabaseAdmin.auth.admin.inviteUserByEmail(email)`,
  then create the local profile row for the returned user id with the
  chosen role. This closes an existing gap (no real invite/reset-link flow
  today) as a direct consequence of the auth swap.

## Web app changes (`app/web/src`)

- Add `@supabase/supabase-js` dependency; new `lib/supabaseClient.ts`
  (project URL + anon key — both public/safe to ship to the browser).
- `stores/useAuthStore.ts`:
  - `login(email, password)` → `supabase.auth.signInWithPassword(...)`
  - `register(name, email, password)` → `supabase.auth.signUp(...)` (name
    passed as user metadata, consumed by the `handle_new_user()` trigger)
  - `logout()` → `supabase.auth.signOut()`
  - add an `onAuthStateChange` subscription so `isAuthenticated`/`user`
    stay correct across tab refresh and token expiry, without polling.
  - `quickLogin(personaId)`: look up the persona's email from
    `/auth/personas`, then `signInWithPassword(email, SEED_PASSWORD)`
    directly — no backend round-trip.
- `api/client.ts`: request interceptor reads
  `(await supabase.auth.getSession()).data.session?.access_token` and sets
  `Authorization: Bearer`; drop cookie-based (`withCredentials`) plumbing.

## Seed data (`packages/prisma/seed.ts`)

The existing `SEED_PASSWORD = "Datacon123!"` constant is kept — it already
matches the "shared demo password" design decision, just needs to be wired
to real Supabase users. For each of the 4 personas
(`sarah`/`david`/`tom`/`maria`):

1. `supabaseAdmin.auth.admin.createUser({ email, password: SEED_PASSWORD, email_confirm: true })`
2. Use the **returned Supabase UUID** as the local `users.id` (replacing
   today's hardcoded slug ids), via a small slug→uuid lookup map — the same
   slugs (`"sarah"`, `"tom"`, ...) are also referenced by
   `DataSource.uploadedById` elsewhere in the seed file, so the map is
   threaded through those references too.

## Infra / environment

- `docker-compose.yml`: remove the `app_postgres` service and
  `app_postgres_data` volume. The file's own comments already treat this
  container as a stand-in "before a Supabase project exists" — that
  project now exists, so both local dev and staging point at Supabase
  Postgres directly. `sample_postgres` / `sample_mysql` / `sample_mongo`
  (external connector fixtures) and `chroma` are untouched.
- Env vars:
  - Remove: `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET`
  - Add: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (web + api),
    `SUPABASE_SERVICE_ROLE_KEY` (api only — must never reach the browser
    bundle)
  - `DATABASE_URL`: Supabase Postgres **direct** connection string (port
    5432) for `datacon-staging-ew` — NestJS is a long-lived process, not
    serverless, so it doesn't need the transaction pooler (port 6543);
    direct connection is simpler and is also required for `prisma migrate`.

## Error handling / edge cases

- Expired/invalid bearer token → `SupabaseAuthGuard` returns 401, same
  contract as today's `JwtAuthGuard`, so existing frontend 401→redirect-to-login
  handling in `api/client.ts` needs no change.
- Admin-invited user who never completes signup: a `public.users` row
  won't exist until the invite is accepted (the trigger fires on
  `auth.users` insert, which happens at invite time, not confirmation) —
  behaves the same as today's "temp password, no real invite" stub, just
  now backed by a real emailed link.
- Self-registration (`signUp`) with an email that already has a pending
  invite: Supabase's own "user already exists" error surfaces through
  `supabase-js`; the web layer surfaces it via the existing toast/error
  path, no new handling needed.

## Testing / verification plan

1. Apply the updated Prisma schema as a migration against
   `datacon-staging-ew` (empty target, no backfill needed).
2. Run `seed.ts` against Supabase; confirm all 4 personas exist in both
   `auth.users` and `public.users` with correct roles.
3. Manual pass via the `run` skill:
   - Register a brand-new user → confirm trigger creates a `viewer`-role
     profile row automatically.
   - Quick-login as each seeded persona.
   - Hit a `manage_users`-gated endpoint as `viewer` (expect 403) and as
     `admin` (expect success).
   - Log out, confirm session clears and protected routes redirect to
     login.
   - Leave a tab open past access-token expiry; confirm `supabase-js`'s
     silent refresh keeps the session alive without user action.

## Explicitly out of scope

- Granular RLS policies (RLS is enabled with zero policies — deny-all for
  anon/authenticated — since the app never queries Postgres from the
  browser; Prisma's privileged connection bypasses RLS entirely).
- `app/ai`'s internal service-to-service auth (`require_internal_auth`).
- The `ConnectorEngine.SUPABASE` customer-data-connector feature.
- Cross-schema FK from `public.users` to `auth.users` (deliberately
  deferred — see Schema changes).
