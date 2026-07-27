# Platform Admin Dashboard Redesign

## Problem

The platform-admin area (`/platform-admin/organizations`, `/platform-admin/organizations/:orgId/users`) was built as a bare-minimum CRUD list during the multi-tenant workspaces work ([[2026-07-24-multi-tenant-workspaces-design]]). It has no stats, no search, no per-org user counts, and the org-users detail page has no way back and doesn't even show which workspace you're looking at. It doesn't read as a SaaS admin console.

This redesign keeps the existing visual system used throughout the app (same `PageHeader`, white-card list containers, `Button`/`Modal`/`RoleBadge`/`Avatar` primitives, `--ac` accent) — no separate "control plane" identity — and makes the two existing pages feel like a real workspace-management dashboard instead of a raw list.

## Scope

In scope:
- `api/src/platform-admin/platform-admin.service.ts`: two additive Prisma query changes (no migration).
- `web/src/api/platformAdmin.ts`: type updates for the new fields.
- `web/src/routes/platform-admin/OrganizationsPage.tsx`: stats row, search, richer rows.
- `web/src/routes/platform-admin/OrgUsersPage.tsx`: breadcrumb, org name in header, real avatars.

Out of scope (explicitly deferred, not part of this pass):
- Workspace status / suspend-reactivate (needs a schema field + auth-relevant logic — separate feature).
- Search/filter-by-role on the detail page.
- A dedicated single-org fetch endpoint — the detail page's org name comes from the already-cached list query, with a graceful fallback when that cache is empty (e.g. hard refresh/direct link).

## Backend changes

`PlatformAdminService.listOrganizations()`:
```ts
this.prisma.scoped.organization.findMany({
  orderBy: { createdAt: "asc" },
  include: { _count: { select: { users: true } } },
});
```
Response shape gains `_count: { users: number }`. The controller passes this through unchanged (no DTO/serialization layer to update — the existing code returns the Prisma result directly).

`PlatformAdminService.listUsers(orgId)`: add `initials: true, avatarGrad: true` to the existing `select` (both columns already exist on `User`, populated at org-creation time — see `initialsFor()` in the same service).

## Frontend changes

### `web/src/api/platformAdmin.ts`

- `Organization` interface gains `_count: { users: number }`.
- `OrgUser` interface gains `initials: string; avatarGrad: string`.

### `OrganizationsPage.tsx`

- **Stats row**: three tiles computed client-side from the `orgs` array already returned by `useOrganizations()` — no new fetch:
  - Workspaces: `orgs.length`
  - Total users: `sum(o._count.users)`
  - New this month: count where `createdAt` falls in the current calendar month
- **Search**: local `useState` filters `orgs` by `name` (case-insensitive substring), no backend param.
- **Rows**: each becomes a card with:
  - An initials chip — orgs have no stored `avatarGrad`, so derive a deterministic background from a small fixed palette (hash of `name` → index), showing the first letters of the org name. This is a local one-off, not a new shared component.
  - Org name (bold)
  - `{n} users` (from `_count.users`)
  - `Created {formatted date}` (from `createdAt`)
  - Existing "Manage users →" link, unchanged behavior.
- Create-workspace modal: unchanged.

### `OrgUsersPage.tsx`

- Breadcrumb `← Workspaces / {org name}`:
  - Reads `useOrganizations()` (React Query cache — already populated when navigating from the list page) and finds the org by `orgId` from the URL param.
  - If the org isn't in cache (direct link / hard refresh with no prior list visit), render just `← Workspaces` with no name segment, and the header falls back to "Workspace users" (today's copy) instead of showing a blank/undefined name. This avoids adding a new single-org endpoint for a cold-load edge case.
- Header: `{org.name} · {users.length} users` when the org is known, else the existing generic copy.
- Rows: use the shared `Avatar` component (from `components/shell/Sidebar.tsx`, already used in `Settings > Users`) with the now-selected `initials`/`avatarGrad`, replacing the current avatar-less row.

## Data flow

No new network calls. Both pages already fetch everything needed; the backend changes only add fields to responses that are already being requested. The detail page's org-name lookup is a cache read (`queryClient` via `useOrganizations()`), not a fetch — if the query hasn't run yet (cold direct link), it will fire in the background per its own hook but the page renders the fallback header immediately rather than blocking on it.

## Visual reference (ui-ux-pro-max design-system)

Concrete spacing/state values pulled from `ui-ux-pro-max:design-system` component specs, adapted to this app's existing CSS-variable system (no Tailwind/shadcn migration — out of scope, see above):

- **Stat tiles**: card padding 20-24px, one per tile in a 3-up row, gap 16px, matching the existing card radius (16px) and border (`1px solid #e9eaf2`) already used for list containers.
- **Row height**: bump from the current ~40px compact row to 56px ("comfortable") now that rows carry an avatar chip + 3 metadata fields, cell padding 12px 16px.
- **Row hover**: subtle background shift (existing `#fafbfe`-style tint already used in `InfoRow`) rather than a border/shadow change, consistent with the rest of the app.
- **Search input**: same `inputStyle` already defined in `settings/UsersPage.tsx` (10px 12px padding, 10px radius, 1px `#e2e4ee` border) — reuse directly, no new input variant.

## Testing

- `api/src/insights/insights.service.spec.ts`-style unit test isn't warranted here — the query changes are additive Prisma `select`/`include` clauses with existing coverage patterns elsewhere in `platform-admin`. Manually verify via the `run` skill: create a workspace, confirm stats/row counts update, open workspace users, confirm breadcrumb + avatars render, confirm search filters correctly.
- No new error states are introduced (existing loading/empty handling is preserved).
