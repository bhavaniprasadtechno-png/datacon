# Multi-tenant workspaces + Platform Admin

**Date:** 2026-07-24
**Status:** Approved, pending implementation plan

## Context

Datacon is currently single-tenant: every signed-up user lands in the same global `users` table, sees the same connectors/data sources/conversations, and "workspace" (used in the Users/Themes admin-page copy) is just a UI label with no backing data model — confirmed by inspecting `schema.prisma` and `UsersService.list()` (`api/src/users/users.service.ts`), which has no tenant filter of any kind.

This spec introduces real multi-tenancy: isolated **workspaces** (called `Organization` in the schema), each with its own users, roles, connectors, uploaded documents, conversations, and feedback, plus a **Platform Admin** role that sits outside every workspace and can provision new workspaces and manage their users.

This builds directly on the Supabase Auth migration (`docs/superpowers/specs/2026-07-22-supabase-auth-migration-design.md`) — `SupabaseAuthGuard`, the existing RBAC (`Role`/`Permission`/`RolePermission`), and the Supabase-hosted Postgres are all extended here, not replaced.

## Decisions

1. **Platform Admin is a separate identity, not an org member.** It lives in its own `PlatformAdmin` table (no `orgId`, not related to `users` at all) — structurally impossible for it to show up in any org-scoped query. It is provisioned directly (one-off script), never via self-registration — nobody can self-elevate to Platform Admin.
2. **One workspace per email, for life.** `User.orgId` is a single required, immutable foreign key. No multi-workspace switching (no join table, no "active workspace" selector).
3. **Signup has no domain logic at all.** Every self-registration (any email, any domain — `gmail.com` and `acme.com` are treated identically) creates a brand-new workspace, with that person as its Admin. The only way into an *existing* workspace is being invited by that workspace's Admin. This sidesteps the "shared free-email domain" problem entirely — there is no domain-based claiming or auto-join to get wrong.
4. **Roles are scoped per workspace.** Each workspace gets its own independent `Viewer`/`Analyst`/`Admin` `Role` rows (renamable/customizable per workspace, invisible across workspaces) via the existing Roles admin page. The `Permission` catalog (the fixed list of capability keys like `manage_users`) stays global — it's app capability, not workspace data.
5. **Platform Admin's reach is Users/Roles only.** It can create workspaces and create/edit/remove users + assign roles in *any* workspace — but has zero visibility into workspace business data (connectors, uploaded documents, conversations, chat, feedback). This is enforced at the RLS layer (see below), not just by convention.
6. **Isolation is enforced twice.** Once explicitly in NestJS (every service filters by `orgId` — the fast, primary gate) and once in Postgres via real RLS policies (the safety net if an app-level filter is ever missed). For RLS to actually mean anything, Prisma must stop connecting as the RLS-bypassing `postgres` role.
7. **New-user provisioning moves out of SQL and into the NestJS app.** The existing `handle_new_user` trigger (from the auth migration) only had to insert one `users` row. Self-registration now has to create an `Organization` + 3 `Role`s + `RolePermission` rows + the `User` row, atomically — this is significantly more logic than belongs in a `plpgsql` trigger function, so it moves to a `POST /auth/complete-registration` endpoint doing one Prisma transaction. The trigger is removed.
8. **Platform Admin UI lives in the same web app**, as a separate `/platform-admin/*` route tree gated on login — not a second deployment. Reuses existing table/dialog components already built for the Users/Roles admin pages.

## Architecture

```
Self-registration (any email)              Invite (existing workspace)
──────────────────────────────              ───────────────────────────
supabase.auth.signUp()                      Org Admin: POST /users
  │                                           │ (validates roleId ∈ own org)
  ▼                                           ▼
POST /auth/complete-registration            supabaseAdmin.auth.admin
  { name, orgName }                            .inviteUserByEmail(...)
  (SupabaseTokenGuard: token-only,              │
   no profile required)                         ▼
  │                                           User row created,
  ▼                                           orgId = inviter's org
Prisma transaction:
  create Organization
  create 3 Roles + RolePermission rows
  create User (orgId, roleId = new Admin)


Platform Admin (separate identity, no org)
───────────────────────────────────────────
POST /platform-admin/organizations              PlatformAdminGuard
  { name, adminEmail, adminName }         ──►   (requires PlatformAdmin row)
  → same provisioning as self-register,
    invite mechanics for adminEmail

GET/POST/PATCH /platform-admin/organizations/:orgId/users
  → explicit :orgId path param (no "current org" to default to)


Per-request org context (every request, org-member or platform-admin)
───────────────────────────────────────────────────────────────────────
NestJS interceptor opens a transaction:
  SET LOCAL app.current_org_id = '<req.user.orgId>';        -- org member
  SET LOCAL app.is_platform_admin = 'true';                 -- platform admin
  <the actual Prisma query, still filtered by orgId explicitly>

Postgres RLS (app_user role — NOT the bypassing `postgres` role):
  users/roles/role_permissions:
    USING (orgId = current_setting('app.current_org_id', true)
           OR current_setting('app.is_platform_admin', true) = 'true')
  connectors/unified_datasets/data_sources/conversations/messages/feedback:
    USING (orgId = current_setting('app.current_org_id', true))
    -- no platform-admin clause: genuinely unreadable to Platform Admin
```

## Schema changes (`packages/prisma/schema.prisma`)

New models:

```prisma
model Organization {
  id        String   @id @default(cuid())
  name      String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  users      User[]
  roles      Role[]
  connectors Connector[]
  datasets   UnifiedDataset[]
  documents  DataSource[]
  conversations Conversation[]
  messages   Message[]
  feedback   Feedback[]

  @@map("organizations")
}

// Deliberately NOT related to User/Organization at all — structurally
// impossible for a platform admin to appear in any org-scoped query.
model PlatformAdmin {
  id        String   @id @db.Uuid // = auth.users.id
  email     String   @unique
  createdAt DateTime @default(now())

  @@map("platform_admins")
}
```

Existing models gain a required, immutable `orgId String` + relation to `Organization`, `@@map`-consistent with today:
`User`, `Role`, `Connector`, `UnifiedDataset`, `DataSource`, `Conversation`, `Message`, `Feedback`.

`RolePermission` is unchanged (scoped transitively via its `Role.orgId`); `Permission` is unchanged (stays global).

## NestJS API changes

**New:**
- `SupabaseTokenGuard` — verifies the bearer token via `getClaims()` only, no local-profile lookup. Used solely by `POST /auth/complete-registration`, the one endpoint that must work before any `users` row exists.
- `PlatformAdminGuard` — verifies the bearer token, requires a matching `PlatformAdmin` row, 403s otherwise. Guards every `/platform-admin/*` route.
- `OrgContextInterceptor` — resolves `req.user.orgId` (or `req.platformAdmin`) and wraps the request in a transaction that runs the appropriate `SET LOCAL`, per the Architecture diagram.
- `AuthController.completeRegistration()`: the Prisma transaction described in Decision 7.
- `PlatformAdminController`: `POST /platform-admin/organizations`, `GET/POST/PATCH /platform-admin/organizations/:orgId/users`.

**Modified:**
- `SupabaseAuthGuard`: checks `PlatformAdmin` first, then `User`; attaches `req.platformAdmin = true` or `req.user = { id, orgId, roleId, permissions }`.
- `UsersService.create()`: validates the chosen `roleId` belongs to the caller's own `orgId` (blocks cross-org role-id guessing) before inviting.
- Every existing service (`UsersService`, `RolesService`, `PermissionsService`, `ConnectorsService`, `DocumentsService`, `ChatService`, `InsightsService`, `ForecastsService`) adds explicit `orgId` filtering to its Prisma queries — the primary gate; RLS is the backstop.

**Removed:** the `handle_new_user`/`on_auth_user_created` Postgres trigger and its migration-time function.

## Web app changes (`app/web/src`)

- `routes/auth/AuthPage.tsx`: register mode gains a required "Workspace name" field; after `supabase.auth.signUp()` succeeds, calls the new `completeRegistration({ name, orgName })`.
- `stores/useAuthStore.ts`: `fetchUser()` reads a `kind: "platform_admin" | "org_member"` discriminator from `/auth/me` and routes accordingly post-login (`/platform-admin` vs `/chat`, unchanged for org members).
- New `routes/platform-admin/`: `OrganizationsPage.tsx` (list + create workspace, invite first Admin), `OrgUsersPage.tsx` (manage a given workspace's users/roles) — reusing the existing table/dialog patterns from `UsersPage.tsx`/`RolesPage.tsx`, pointed at `:orgId`-scoped endpoints.

## Infra / Postgres role change

- New dedicated Postgres role (e.g. `app_user`) **without** `BYPASSRLS`, replacing the `postgres` superuser role in `DATABASE_URL`/`DIRECT_URL`. Without this, the RLS policies below are decorative — Postgres skips RLS entirely for any role with `BYPASSRLS`.
- Migration adds `org_isolation` policies to every org-scoped table (see Architecture diagram for the exact `USING` clauses, including the Platform Admin bypass clause limited to `users`/`roles`/`role_permissions`). `role_permissions` has no `orgId` of its own — its policy joins to its `Role`'s `orgId` instead: `USING (EXISTS (SELECT 1 FROM roles r WHERE r.id = role_permissions."roleId" AND (r."orgId" = current_setting('app.current_org_id', true) OR current_setting('app.is_platform_admin', true) = 'true')))`.

## Seed data (`packages/prisma/seed.ts`)

- Create one `Organization` ("Acme Corp") and scope the 4 existing personas (sarah/david/tom/maria) + all existing connectors/datasets/data-sources/conversations to it, unchanged otherwise.
- Create one `PlatformAdmin` row + matching Supabase Auth user (e.g. `platform-admin@datacon.internal`, same `SEED_PASSWORD` for demo purposes) — not a member of Acme Corp or any org.

## Error handling / edge cases

- `complete-registration` fails after `signUp()` already succeeded: the auth user exists with no `users` row yet. The web app detects "authenticated but no profile" and shows a "finish setting up your workspace" screen that retries `complete-registration` — idempotent (no-ops if a `User` row already exists for that auth id).
- An org Admin invites a user with a `roleId` belonging to a different org: rejected by `UsersService.create()`'s new org-match check before any Supabase invite is sent.
- A Platform Admin session directly querying `data_sources`/`connectors`/`conversations`/`messages`/`feedback`: RLS returns zero rows regardless of app-level code, since those tables' policies have no platform-admin clause.
- No org context set at all (a bug lets a request through without the interceptor running): `current_setting(..., true)` returns `NULL`, every `org_isolation` policy evaluates false, zero rows visible — fails closed, not open.

## Testing / verification plan

1. Two workspaces exist (seeded "Acme Corp" + a freshly self-registered "Test Co") — confirm zero cross-visibility of users, connectors, documents, and conversations, both via the API and via a direct Postgres query run as the new `app_user` role.
2. Platform Admin: can list/create workspaces and create/edit users in both Acme Corp and Test Co; a query against `data_sources`/`connectors`/`conversations` under the Platform Admin's session context returns zero rows.
3. Self-registration end-to-end: a new email produces a new org + Admin role, confirmed via `/auth/me`.
4. Invite-only join confirmed: an org Admin's invite creates a user scoped to the correct org; no code path lets an email join an *existing* workspace without an invite (self-registration always makes a new org, regardless of email domain).
5. Cross-org role-id guessing blocked: an org Admin attempting to assign a role ID belonging to a different org is rejected.

## Explicitly out of scope

- Multi-workspace membership per user (one workspace per email, for life — no "switch workspace" UI).
- Platform Admin visibility into workspace business data (connectors, uploaded documents, conversations, chat, feedback) — Users/Roles only.
- Per-workspace custom permission catalog (the `Permission` table stays global; only `Role` assignment/customization is per-workspace).
- Billing/plan tiers per workspace.
- Domain-based auto-join or domain claiming of any kind (dropped in favor of pure invite-only joining).
