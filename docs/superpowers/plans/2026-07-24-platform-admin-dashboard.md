# Platform Admin Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the bare-list platform-admin pages (`/platform-admin/organizations`, `/platform-admin/organizations/:orgId/users`) into a real workspace-management dashboard — stats, search, richer rows, breadcrumb — using the app's existing visual system (no new component library, no shadcn/Tailwind migration).

**Architecture:** Two additive Prisma query changes expose `userCount` per org and `initials`/`avatarGrad` per org-user (both columns already exist on `User`). The two existing React pages are rewritten in place to consume the richer payloads; all new visuals (stat tiles, search input, avatar chips, breadcrumb) reuse existing primitives (`Button`, `Avatar`, `PageHeader`, `inputStyle`) or are small local pieces of the same page file — no new shared component files.

**Tech Stack:** NestJS + Prisma (`api/`), React + `@tanstack/react-query` + inline-style CSS-variable system (`web/`). No Tailwind/shadcn in this codebase — do not introduce it.

## Global Constraints

- No new dependencies, no shadcn/Tailwind migration (see spec's "Backend changes"/"Frontend changes" — visual reference is adapted to the existing CSS-variable system, not implemented via Tailwind).
- No schema migration — `userCount`, `initials`, `avatarGrad` are all sourced from existing columns/relations.
- No new endpoints — the org-users detail page gets the org name from the already-cached `useOrganizations()` list query, with a fallback when that cache is empty (direct link / hard refresh).
- Workspace status/suspend and role-filter search on the detail page are explicitly out of scope for this plan (see spec).
- Reference spec: `docs/superpowers/specs/2026-07-24-platform-admin-dashboard-design.md`.

---

### Task 1: Backend — expose `userCount` and avatar fields

**Files:**
- Modify: `api/src/platform-admin/platform-admin.service.ts:32-34` (`listOrganizations`)
- Modify: `api/src/platform-admin/platform-admin.service.ts:76-82` (`listUsers`)

**Interfaces:**
- Produces: `listOrganizations()` now resolves `Array<{ id: string; name: string; createdAt: Date; updatedAt: Date; _count: { users: number } }>`.
- Produces: `listUsers(orgId)` now resolves `Array<{ id: string; name: string; email: string; roleId: string; initials: string; avatarGrad: string; role: { name: string } }>`.
- Consumed by: Task 2 (frontend types), which mirrors these exact shapes.

- [ ] **Step 1: Update `listOrganizations` to include the user count**

In `api/src/platform-admin/platform-admin.service.ts`, replace:

```ts
  async listOrganizations() {
    return this.prisma.scoped.organization.findMany({ orderBy: { createdAt: "asc" } });
  }
```

with:

```ts
  async listOrganizations() {
    return this.prisma.scoped.organization.findMany({
      orderBy: { createdAt: "asc" },
      include: { _count: { select: { users: true } } },
    });
  }
```

- [ ] **Step 2: Update `listUsers` to select avatar fields**

In the same file, replace:

```ts
  async listUsers(orgId: string) {
    return this.prisma.scoped.user.findMany({
      where: { orgId },
      select: { id: true, name: true, email: true, roleId: true, role: { select: { name: true } } },
      orderBy: { createdAt: "asc" },
    });
  }
```

with:

```ts
  async listUsers(orgId: string) {
    return this.prisma.scoped.user.findMany({
      where: { orgId },
      select: {
        id: true,
        name: true,
        email: true,
        roleId: true,
        initials: true,
        avatarGrad: true,
        role: { select: { name: true } },
      },
      orderBy: { createdAt: "asc" },
    });
  }
```

- [ ] **Step 3: Verify with a manual API check (no unit test — see rationale)**

These are additive `select`/`include` clauses with no branching logic, so a Prisma-mocking unit test would only assert the query object shape, not real behavior — not worth it per the approved spec's Testing section. Instead, verify directly:

Run: `cd api && npm run start:dev`

Then, as a platform admin, hit:
```
GET /platform-admin/organizations
GET /platform-admin/organizations/:orgId/users
```

Expected: the first response's items each include `_count: { users: <number> }`; the second response's items each include `initials` and `avatarGrad` string fields.

- [ ] **Step 4: Commit**

```bash
git add api/src/platform-admin/platform-admin.service.ts
git commit -m "feat: expose user counts and avatar fields from platform-admin API"
```

---

### Task 2: Frontend — update API types and hooks

**Files:**
- Modify: `web/src/api/platformAdmin.ts` (full file, 41 lines)

**Interfaces:**
- Consumes: the response shapes produced by Task 1.
- Produces: `Organization` type with `_count: { users: number }`; `OrgUser` type with `initials: string; avatarGrad: string`. Both are re-exported from this module and imported by Tasks 3 and 4.

- [ ] **Step 1: Update the `Organization` and `OrgUser` interfaces**

Replace the top of `web/src/api/platformAdmin.ts`:

```ts
interface Organization {
  id: string;
  name: string;
  createdAt: string;
}

interface OrgUser {
  id: string;
  name: string;
  email: string;
  roleId: string;
  role: { name: string };
}
```

with:

```ts
export interface Organization {
  id: string;
  name: string;
  createdAt: string;
  _count: { users: number };
}

export interface OrgUser {
  id: string;
  name: string;
  email: string;
  roleId: string;
  initials: string;
  avatarGrad: string;
  role: { name: string };
}
```

(Exporting both interfaces so the page components in Tasks 3 and 4 can type local helpers against them, e.g. a `(org: Organization) => ...` filter function.)

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no new errors (the hooks below this point already reference `Organization`/`OrgUser` structurally, so this should pass once Task 1's API is live; if run before Task 1 is deployed, the shapes are still valid TypeScript since they only describe the client-side type, not runtime data).

- [ ] **Step 3: Commit**

```bash
git add web/src/api/platformAdmin.ts
git commit -m "feat: type user counts and avatar fields in platformAdmin API client"
```

---

### Task 3: `OrganizationsPage` — stats row, search, richer rows

**Files:**
- Modify: `web/src/routes/platform-admin/OrganizationsPage.tsx` (full file, 63 lines)

**Interfaces:**
- Consumes: `Organization` type and `useOrganizations()`/`useCreateOrganization()` hooks from Task 2 (`web/src/api/platformAdmin.ts`).
- Consumes: `PageHeader`, `FieldRow`, `inputStyle` from `web/src/routes/settings/UsersPage.tsx` (already imported today, unchanged).
- Consumes: `Button` from `web/src/components/ui/Button.tsx` (unchanged).

- [ ] **Step 1: Add a deterministic org-initials chip color helper**

At the top of `OrganizationsPage.tsx` (after the imports), add:

```ts
const CHIP_PALETTE = ["#5b5fc7", "#0f8a5c", "#c0405a", "#b8791f", "#2178c9"];

function chipColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return CHIP_PALETTE[hash % CHIP_PALETTE.length];
}

function orgInitials(name: string): string {
  const words = name.trim().split(/\s+/).slice(0, 2);
  return words.map((w) => w[0]?.toUpperCase() ?? "").join("") || "W";
}
```

- [ ] **Step 2: Add a search input and derive filtered/stat values**

Inside the `OrganizationsPage` component, after the existing `useState` calls, add:

```ts
  const [search, setSearch] = useState("");
  const filteredOrgs = (orgs ?? []).filter((o) => o.name.toLowerCase().includes(search.trim().toLowerCase()));

  const now = new Date();
  const newThisMonth = (orgs ?? []).filter((o) => {
    const d = new Date(o.createdAt);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }).length;
  const totalUsers = (orgs ?? []).reduce((sum, o) => sum + o._count.users, 0);
```

- [ ] **Step 3: Render the stats row between `PageHeader` and the search input**

Replace:

```tsx
      <PageHeader title="Workspaces" sub="Create and manage every organization on the platform" action={<Button variant="primary" onClick={() => setCreating(true)}>+ Create workspace</Button>} />
      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
```

with:

```tsx
      <PageHeader title="Workspaces" sub="Create and manage every organization on the platform" action={<Button variant="primary" onClick={() => setCreating(true)}>+ Create workspace</Button>} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 20 }}>
        <StatTile label="Workspaces" value={orgs?.length ?? 0} />
        <StatTile label="Total users" value={totalUsers} />
        <StatTile label="New this month" value={newThisMonth} />
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search workspaces..."
        style={{ ...inputStyle, marginBottom: 16 }}
      />

      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
```

- [ ] **Step 4: Replace the row rendering to use `filteredOrgs` and show the richer row**

Replace:

```tsx
        {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}
        {orgs?.map((o) => (
          <Link key={o.id} to={`/platform-admin/organizations/${o.id}/users`} style={{ display: "flex", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid #f5f6fb" }}>
            <span style={{ fontWeight: 700, fontSize: 13.5 }}>{o.name}</span>
            <span style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12.5 }}>Manage users →</span>
          </Link>
        ))}
```

with:

```tsx
        {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}
        {!isLoading && filteredOrgs.length === 0 && (
          <div style={{ padding: 20, color: "#9499ad", fontSize: 13 }}>No workspaces match "{search}".</div>
        )}
        {filteredOrgs.map((o) => (
          <Link
            key={o.id}
            to={`/platform-admin/organizations/${o.id}/users`}
            style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px", minHeight: 56, borderBottom: "1px solid #f5f6fb" }}
          >
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: "50%",
                background: chipColor(o.name),
                color: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 700,
                fontSize: 13,
                flexShrink: 0,
              }}
            >
              {orgInitials(o.name)}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 13.5 }}>{o.name}</div>
              <div style={{ fontSize: 11.5, color: "#9499ad" }}>
                {o._count.users} {o._count.users === 1 ? "user" : "users"} · Created{" "}
                {new Date(o.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
              </div>
            </div>
            <span style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12.5, flexShrink: 0 }}>Manage users →</span>
          </Link>
        ))}
```

- [ ] **Step 5: Add the local `StatTile` component**

At the bottom of the same file (after the `OrganizationsPage` function, before end of file), add:

```tsx
function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e9eaf2", borderRadius: 16, padding: "20px 22px" }}>
      <div style={{ font: "600 10.5px 'IBM Plex Mono',monospace", letterSpacing: ".06em", color: "#9499ad", marginBottom: 8 }}>
        {label.toUpperCase()}
      </div>
      <div style={{ fontSize: 26, fontWeight: 800 }}>{value}</div>
    </div>
  );
}
```

- [ ] **Step 6: Typecheck and manually verify**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

Then start the app (see the `run` skill) and open `/platform-admin/organizations` as a platform admin. Expected:
- Three stat tiles show correct counts.
- Typing in the search box filters rows by name live.
- Each row shows an initials chip, user count, and created date.
- Creating a new workspace still works and the new row appears with `0 users`/today's date and updates the stats.

- [ ] **Step 7: Commit**

```bash
git add web/src/routes/platform-admin/OrganizationsPage.tsx
git commit -m "feat: add stats, search, and richer rows to the workspaces list"
```

---

### Task 4: `OrgUsersPage` — breadcrumb, org header, real avatars

**Files:**
- Modify: `web/src/routes/platform-admin/OrgUsersPage.tsx` (full file, 27 lines)

**Interfaces:**
- Consumes: `OrgUser` type and `useOrgUsers()` from Task 2.
- Consumes: `useOrganizations()` from `web/src/api/platformAdmin.ts` (already exists) to read the org name out of the React Query cache.
- Consumes: `Avatar` from `web/src/components/shell/Sidebar.tsx` — signature `({ grad, initials, size, ring }: { grad: string; initials: string; size: number; ring?: boolean })` (exported, already used by `UsersPage.tsx`).
- Consumes: `PageHeader` from `web/src/routes/settings/UsersPage.tsx`.

- [ ] **Step 1: Rewrite the page**

Replace the full contents of `web/src/routes/platform-admin/OrgUsersPage.tsx` with:

```tsx
import { Link, useParams } from "react-router-dom";
import { useOrganizations, useOrgUsers } from "../../api/platformAdmin";
import { PageHeader } from "../settings/UsersPage";
import { RoleBadge } from "../../components/ui/RoleBadge";
import { Avatar } from "../../components/shell/Sidebar";

export function OrgUsersPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { data: users, isLoading } = useOrgUsers(orgId);
  const { data: orgs } = useOrganizations();
  const org = orgs?.find((o) => o.id === orgId);

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "#9499ad", marginBottom: 14 }}>
        <Link to="/platform-admin/organizations" style={{ color: "#9499ad" }}>
          ← Workspaces
        </Link>
        {org && (
          <>
            <span>/</span>
            <span style={{ color: "var(--ac-fg)", fontWeight: 600 }}>{org.name}</span>
          </>
        )}
      </div>
      <PageHeader
        title={org ? org.name : "Workspace users"}
        sub={`${users?.length ?? 0} ${users?.length === 1 ? "user" : "users"} in this organization`}
      />
      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
        {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}
        {users?.map((u) => (
          <div key={u.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 18px", minHeight: 56, borderBottom: "1px solid #f5f6fb" }}>
            <Avatar grad={u.avatarGrad} initials={u.initials} size={34} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{u.name}</div>
              <div style={{ fontSize: 11.5, color: "#9499ad" }}>{u.email}</div>
            </div>
            <RoleBadge name={u.role.name} color={null} bg={null} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck and manually verify**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

Then, as a platform admin: navigate from `/platform-admin/organizations` into a workspace's users. Expected:
- Breadcrumb reads `← Workspaces / <Org Name>`.
- Page title is the org name, subtitle shows the user count.
- Each row shows a real colored avatar with initials (matching `Settings > Users`), not a bare name.
- Clicking `← Workspaces` returns to the list.
- Hard-refreshing directly on the users URL (cold cache) still renders — breadcrumb shows only `← Workspaces` and title falls back to "Workspace users" instead of crashing or showing "undefined".

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/platform-admin/OrgUsersPage.tsx
git commit -m "feat: add breadcrumb, org header, and real avatars to workspace users page"
```

---

## Self-Review Notes

- **Spec coverage:** Backend `_count`/avatar fields (Task 1), frontend types (Task 2), stats/search/rows (Task 3), breadcrumb/header/avatars (Task 4) — all sections of the spec are covered. Out-of-scope items (status/suspend, role filter, dedicated single-org endpoint) are intentionally not tasked, per spec.
- **Placeholder scan:** No TBD/TODO; every step has literal code.
- **Type consistency:** `Organization._count.users` (Task 1/2) is consumed identically in Task 3 (`o._count.users`). `OrgUser.initials`/`avatarGrad` (Task 1/2) match the `Avatar` component's prop names exactly (Task 4). `useOrganizations()` is reused as-is (no signature change) by both Task 3 and Task 4.
