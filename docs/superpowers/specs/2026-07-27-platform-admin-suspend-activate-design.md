# Platform Admin: Suspend/Activate for Workspaces and Users

## Problem

The platform-admin area has no way to disable a workspace or a single user. `OrganizationsPage` and `OrgUsersPage` ([[2026-07-24-platform-admin-dashboard-design]]) only support create/list — every org and every user is permanently active once created. The mockup referenced in [[2026-07-24-platform-admin-shell-dashboard-design]] (`claude.ai/design/p/9e74661c-f4b4-4a22-b1d9-469772551a21`, `Datacon.dc.html`) shows a cross-org admin table with suspend/activate per admin — that spec explicitly deferred this ("Sub-project 2 ... needs a real suspend concept on `User` plus an auth-enforcement change"). This spec builds that concept, scoped to the two pages that already exist rather than the mockup's separate cross-org table.

## Decisions from brainstorming

1. **Scope: both levels.** Suspend/activate applies to entire workspaces (on `OrganizationsPage`) and to individual users within a workspace (on `OrgUsersPage`) — two independent toggles, not a cascading write (see Data model).
2. **Enforcement: blocks login, not just a UI flag.** A suspended user (or any user in a suspended org) is rejected at the API layer, not just shown a badge.
3. **"Active Organizations" KPI** on `PlatformOverviewPage` changes from counting all orgs to counting only `status === "ACTIVE"` orgs, since that's what the label says.

## Data model

One shared enum, one field added to each of the two existing models — additive migration, default `ACTIVE`, no backfill logic:

```prisma
enum AccountStatus {
  ACTIVE
  SUSPENDED
}

model Organization {
  // ...existing fields
  status AccountStatus @default(ACTIVE)
}

model User {
  // ...existing fields
  status AccountStatus @default(ACTIVE)
}
```

`Organization.status` and `User.status` are independent — suspending a workspace does not write to every `User` row in it. Effective "is this request allowed" is computed at enforcement time as `user.status === SUSPENDED || user.org.status === SUSPENDED` (see Auth enforcement). This avoids a bulk-write fan-out and keeps "who did the platform admin actually suspend" auditable-in-principle (even though no audit log exists yet — out of scope).

## Backend changes

`PlatformAdminService` (`api/src/platform-admin/platform-admin.service.ts`):
- `setOrganizationStatus(orgId: string, status: AccountStatus)` — `this.prisma.scoped.organization.update({ where: { id: orgId }, data: { status } })`.
- `setUserStatus(userId: string, status: AccountStatus)` — `this.prisma.scoped.user.update({ where: { id: userId }, data: { status } })`.
- `listOrganizations()` and `listUsers(orgId)` both add `status: true` to their existing `select`/return shape.

`PlatformAdminController` (`api/src/platform-admin/platform-admin.controller.ts`):
- `PATCH /platform-admin/organizations/:orgId/status` — body validated by a small `UpdateStatusDto` (`@IsEnum(AccountStatus) status`).
- `PATCH /platform-admin/organizations/:orgId/users/:userId/status` — same DTO.

No new module/controller — both routes live on the existing `PlatformAdminController`, guarded by the existing `PlatformAdminGuard` (unchanged).

## Auth enforcement

Two call sites, same check, both already load the row they need to check (no new query):

- **`SupabaseAuthGuard`** (`api/src/auth/guards/supabase-auth.guard.ts`) — runs on every org-scoped request. Its existing `prisma.user.findUnique` gains `org: { select: { status: true } }` in its `include`. After loading, if `user.status === "SUSPENDED"` or `user.org.status === "SUSPENDED"`, throw `ForbiddenException("This account has been suspended.")` instead of setting `req.user`. This blocks an already-logged-in suspended user on their very next API call, not just their next login.
- **`AuthService.me()`** (`api/src/auth/auth.service.ts`) — same check against the `user` it already loads via `userWithPermissions`. Throwing here means `fetchUser()` (called on every app load and on every Supabase auth-state change) fails immediately for a suspended account, so the frontend simply falls back to the logged-out state — no dedicated "you are suspended" screen needed.
- Platform admins are unaffected — `PlatformAdminGuard` has no status concept and none is added; suspension only applies to `User`/`Organization`.

**Known gap (accepted for this pass):** a user suspended mid-session keeps working until their next API call passes through `SupabaseAuthGuard` — there is no push-based session kill (e.g. a websocket signal or forced Supabase sign-out). Given this app's request-per-page-load pattern, that's within a few seconds to the next navigation in practice; a real-time kill switch is not built.

## Frontend changes

### `web/src/api/platformAdmin.ts`
- `Organization` interface gains `status: "ACTIVE" | "SUSPENDED"`.
- `OrgUser` interface gains the same.
- New mutation hooks: `useSetOrganizationStatus()`, `useSetUserStatus()` — both invalidate the same query keys their sibling create/list hooks already use.

### `OrganizationsPage.tsx`
- Each row gains a status badge and a Suspend/Activate button, placed before the existing "Manage users →" affordance.
- The button calls `e.preventDefault(); e.stopPropagation()` before acting, since the row itself is a `<Link>` (same pattern as `Sidebar.tsx`'s `removeConversation`).
- Suspending asks for confirmation via the existing `useConfirm()` (`tone: "danger"`, body: "All users in this workspace will be immediately blocked from signing in."). Activating does not prompt — it's non-destructive and immediately reversible.

### `OrgUsersPage.tsx`
- Each row gains the same badge + button, scoped to that one user's `status`. Confirm-on-suspend, no confirm on activate, same copy pattern ("They will be immediately blocked from signing in.").

### Shared piece
- A small `StatusBadge` (new, next to `RoleBadge.tsx` since it's the closest existing precedent — pill shape, uppercase text, muted colors: green-ish for `ACTIVE`, red-ish for `SUSPENDED`). Not a new shared component *system* — just one small file, following `RoleBadge`'s existing shape.

### `PlatformOverviewPage.tsx`
- "ACTIVE ORGANIZATIONS" KPI changes from `orgs?.length` to `orgs?.filter(o => o.status === "ACTIVE").length`. The "new this month" trend line is unaffected (still counts all new orgs regardless of status).

## Testing

- Backend: extend `platform-admin.guard.spec.ts`-style unit tests (or a new spec) for `SupabaseAuthGuard` covering the new suspended-user and suspended-org rejection paths — this is real branching logic, unlike the additive `select` changes in the earlier dashboard-redesign spec, so it earns a unit test.
- Frontend: no component tests exist elsewhere in `web/` (established pattern) — verify via `tsc --noEmit` plus a manual browser walkthrough: suspend a user, confirm they're logged out on next action; suspend a workspace, confirm all its users are blocked; activate both, confirm access returns; confirm the Dashboard's Active Organizations count drops when a workspace is suspended.

## Out of scope

- No audit log of who suspended what and when.
- No email/notification to the affected user or workspace.
- No bulk suspend/activate (one row at a time only).
- No real-time/push session kill for an already-open tab (see Known gap above).
- No change to `PlatformAdminGuard`/platform admin accounts — they have no status concept.
