# Platform Admin Shell + Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the platform-admin area a real navigation shell (fixing the missing-logout bug) and a Dashboard page, matching the dark-sidebar "Super Admin" console from the user-supplied Claude Design mockup, with real data where it exists and explicit mock values where it doesn't.

**Architecture:** Tailwind CSS v4 + shadcn/ui (Radix base, "nova" preset) were added to `web/`, scoped so they only affect new platform-admin files — every existing page keeps its inline-style/CSS-variable system untouched (verified: Tailwind's `@layer base` styles lose to the app's existing unlayered CSS in the cascade, and shadcn's `Card`/`Button`/`Badge` primitives live in a separate `@/components/shadcn-ui/ui` folder so they never collide with the app's own `@/components/ui`). A new `PlatformAdminShell` layout component (dark sidebar + `<Outlet/>`, plain Tailwind classes — not the shadcn "sidebar" block, which pulls in `@base-ui/react` and offcanvas/mobile/cookie machinery this app doesn't need) wraps all `/platform-admin/*` routes in `App.tsx`. The existing `OrganizationsPage`/`OrgUsersPage` move under this shell unchanged (relabeled "Admin users" in the nav, inline-style as before — this plan does not retroactively convert them). A new `PlatformOverviewPage` becomes the Dashboard using shadcn `Card`, and a tiny `ComingSoonPage` placeholder covers the not-yet-built "Subscription plans"/"Providers" sections.

**Tech Stack:** React + react-router-dom + `@tanstack/react-query`; Tailwind CSS v4 (`@tailwindcss/vite`) + shadcn/ui (Radix base) for new platform-admin files only; existing inline-style/CSS-variable system unchanged everywhere else.

## Global Constraints

- Match the mockup's exact values verbatim (colors, copy, mock data) — see `docs/superpowers/specs/2026-07-24-platform-admin-shell-dashboard-design.md` "Source of truth" section. One-off mockup colors (`#1a1730`, `#8f89c2`, etc.) are applied via Tailwind arbitrary-value classes (`bg-[#1a1730]`), not new semantic design tokens — that would be a separate design-system project.
- **`components.json`'s `ui`/`components` aliases must stay pointed at `@/components/shadcn-ui[/ui]`, never `@/components/ui`.** On a case-insensitive filesystem (this repo is developed on Windows), `npx shadcn add button` writing to the default `@/components/ui` path silently overwrites this app's own hand-rolled `Button.tsx`/`Modal.tsx`/`RoleBadge.tsx` (`Button.tsx` and `button.tsx` are the same file). This was caught and fixed during Task 0 — do not revert `components.json`'s aliases back to the default.
- Active Organizations (value + trend) and Total Users (value only, no trend) use real data via the existing `useOrganizations()` hook (`web/src/api/platformAdmin.ts`). MRR, Churn Rate, revenue-by-plan, and the activity feed are hardcoded mock constants — no new backend endpoints.
- Sub-projects 2-4 (Admin users redesign, Subscription plans, Providers) are explicitly out of scope — this plan only builds the shell, Dashboard, and placeholders.
- Reference spec: `docs/superpowers/specs/2026-07-24-platform-admin-shell-dashboard-design.md`.

---

### Task 0: Tailwind CSS + shadcn/ui setup (scoped, non-colliding)

**Status: already completed during this plan's execution** — recorded here for reference/reproducibility, not as a pending step.

**Files:**
- Modify: `web/package.json` (added `tailwindcss`, `@tailwindcss/vite`, `class-variance-authority`, `radix-ui`, plus shadcn's own dependency additions)
- Modify: `web/vite.config.ts` — added `@tailwindcss/vite` plugin and a `@` → `./src` resolve alias
- Modify: `web/tsconfig.json`, `web/tsconfig.app.json` — added `"paths": {"@/*": ["./src/*"]}` (no `baseUrl` — deprecated under `moduleResolution: "bundler"`)
- Modify: `web/src/index.css` — shadcn's generated theme block (oklch CSS variables, `@layer base` reset) prepended above the app's existing `@import "./styles/tokens.css";`
- Create: `web/components.json` — **`aliases.ui` set to `@/components/shadcn-ui/ui` and `aliases.components` to `@/components/shadcn-ui`** (not the shadcn default `@/components/ui`) to avoid the Windows case-collision described above
- Create: `web/src/lib/utils.ts` (shadcn's `cn()` helper)
- Create: `web/src/components/shadcn-ui/ui/button.tsx`, `card.tsx`, `badge.tsx` (via `npx shadcn@latest add button card badge`)

Commands used:
```bash
npm install tailwindcss @tailwindcss/vite
npx shadcn@latest init -t vite -b radix -p nova -y
# (init requires Tailwind + a path alias to already be configured — do those manually first, see files above)
# then, after fixing components.json's aliases:
npx shadcn@latest add button card badge -y
```

**Verification performed:**
- `cd web && npx tsc --noEmit` — clean.
- `git status` confirmed `web/src/components/ui/` (the app's own components) has zero changes after setup.
- Logged into the running app as a regular org member (`tom@acme.com` / seed password) and confirmed the Chat page, Sidebar, and buttons render identically to before — Tailwind's layered CSS does not visually affect existing inline-styled pages.

---

### Task 1: `PlatformAdminShell` — dark sidebar shell (Tailwind), wired into routing

**Files:**
- Create: `web/src/components/shell/PlatformAdminShell.tsx`
- Modify: `web/src/App.tsx`

**Interfaces:**
- Consumes: `useAuth()` from `web/src/stores/useAuthStore.ts` — `{ user, logout }`, where `user` for a platform admin is `{ kind: "platform_admin"; id: string; email: string }` (from `web/src/lib/types.ts`).
- Consumes: `Button` from `web/src/components/shadcn-ui/ui/button.tsx` (shadcn, Radix-based, `variant`/`size`/`className` props — see Task 0).
- Produces: `PlatformAdminShell` — a layout route element rendering `<Outlet/>` for nested routes.

- [x] **Step 1: Create the shell component**

`web/src/components/shell/PlatformAdminShell.tsx`:

```tsx
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../stores/useAuthStore";
import { Button } from "../shadcn-ui/ui/button";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: "📊", to: "/platform-admin/dashboard" },
  { id: "admins", label: "Admin users", icon: "👤", to: "/platform-admin/organizations" },
  { id: "plans", label: "Subscription plans", icon: "💳", to: "/platform-admin/plans" },
  { id: "providers", label: "Providers", icon: "🔌", to: "/platform-admin/providers" },
];

export function PlatformAdminShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const email = user?.kind === "platform_admin" ? user.email : "";

  const handleSignOut = async () => {
    await logout();
    navigate("/");
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <aside className="flex w-[236px] shrink-0 flex-col bg-[#1a1730] p-3.5 text-white">
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex size-[34px] shrink-0 items-center justify-center rounded-[10px] bg-gradient-to-br from-[#6d4dff] to-[#2bb8c4] text-base font-extrabold">
            D
          </div>
          <div className="min-w-0">
            <div className="text-[15px] font-extrabold">Datacon</div>
            <div className="font-mono text-[9.5px] font-semibold tracking-[.12em] text-[#8f89c2]">SUPER ADMIN</div>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5">
          {NAV.map((item) => {
            const active = location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.id}
                to={item.to}
                className={`flex items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-[13.5px] no-underline ${
                  active ? "bg-white/10 font-bold text-white" : "font-medium text-[#b7b2dd]"
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="mt-3.5 border-t border-white/10 pt-3.5">
          <div className="mb-2.5 flex items-center gap-2.5">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#6d4dff] to-[#8c6eff] text-[13px] font-bold">
              {email.charAt(0).toUpperCase() || "S"}
            </div>
            <div className="min-w-0">
              <div className="truncate text-[12.5px] font-bold">{email}</div>
              <div className="text-[10.5px] text-[#8f89c2]">Platform Admin</div>
            </div>
          </div>
          <Button
            onClick={handleSignOut}
            variant="ghost"
            className="w-full justify-center gap-1.5 bg-white/5 text-[12.5px] font-bold text-[#ff8fa3] hover:bg-white/10 hover:text-[#ff8fa3]"
          >
            ⏻ Sign out
          </Button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto bg-[var(--ac-bg)]">
        <Outlet />
      </main>
    </div>
  );
}
```

(Uses `shrink-0`, `gap-*` per shadcn's own styling rules — no `space-x-*`/`space-y-*`. Note: this deliberately does **not** use the shadcn `Sidebar`/`SidebarProvider` block — that component pulls in `@base-ui/react` plus mobile-sheet/cookie-persistence/keyboard-shortcut machinery this fixed, always-visible admin nav doesn't need. Plain Tailwind-classed markup is the leaner fit here.)

- [x] **Step 2: Wire the shell into `App.tsx`'s route tree**

Added imports:

```tsx
import { OrganizationsPage } from "./routes/platform-admin/OrganizationsPage";
import { OrgUsersPage } from "./routes/platform-admin/OrgUsersPage";
import { PlatformOverviewPage } from "./routes/platform-admin/PlatformOverviewPage";
import { ComingSoonPage } from "./routes/platform-admin/ComingSoonPage";
import { PlatformAdminShell } from "./components/shell/PlatformAdminShell";
```

Replaced the two standalone `/platform-admin*` routes with a layout route (Tasks 1-3 landed together in implementation, so the final route tree includes all of them in one edit):

```tsx
      <Route
        element={
          <RequirePlatformAdmin>
            <PlatformAdminShell />
          </RequirePlatformAdmin>
        }
      >
        <Route path="/platform-admin" element={<Navigate to="/platform-admin/dashboard" replace />} />
        <Route path="/platform-admin/dashboard" element={<PlatformOverviewPage />} />
        <Route path="/platform-admin/organizations" element={<OrganizationsPage />} />
        <Route path="/platform-admin/organizations/:orgId/users" element={<OrgUsersPage />} />
        <Route path="/platform-admin/plans" element={<ComingSoonPage title="Subscription plans" />} />
        <Route path="/platform-admin/providers" element={<ComingSoonPage title="Providers" />} />
      </Route>
```

`RequirePlatformAdmin` itself is unchanged — it now wraps the shell instead of individual pages.

- [x] **Step 3: Typecheck** — `cd web && npx tsc --noEmit` — clean.

- [x] **Step 4: Manually verify** (via `claude-in-chrome`, logged in as the seeded platform admin `platform-admin@datacon.internal`):
- Landing on `/platform-admin` redirects to `/platform-admin/dashboard`, dark 236px sidebar renders (`#1a1730`).
- "Admin users" nav item highlights on `/platform-admin/organizations`.
- Bottom of sidebar shows the platform admin's email and a "⏻ Sign out" button.
- Clicking "Sign out" logs out and lands on `/` (the real auth page) — confirmed fixed.
- "Subscription plans"/"Providers" nav items render the coming-soon placeholder (Task 3) instead of 404ing.

- [ ] **Step 5: Commit** (not yet done — per project convention, only commit when explicitly asked)

---

### Task 2: `PlatformOverviewPage` — Dashboard with real + mock KPIs (shadcn `Card`)

**Files:**
- Create: `web/src/routes/platform-admin/PlatformOverviewPage.tsx`

**Interfaces:**
- Consumes: `useOrganizations()` and `Organization` type from `web/src/api/platformAdmin.ts` — `{ id, name, createdAt, _count: { users: number } }`.
- Consumes: `PageHeader` from `web/src/routes/settings/UsersPage.tsx`.
- Consumes: `Card`, `CardContent`, `CardHeader`, `CardTitle` from `web/src/components/shadcn-ui/ui/card.tsx`.

- [x] **Step 1: Create the Dashboard page**

```tsx
import { useOrganizations } from "../../api/platformAdmin";
import { PageHeader } from "../settings/UsersPage";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/shadcn-ui/ui/card";

const MOCK_MRR = { label: "MONTHLY RECURRING REVENUE", value: "$284,900", trend: "↑ 12.4% vs last month" };
const MOCK_CHURN = { label: "CHURN RATE", value: "1.8%", trend: "↓ 0.3pt improved" };

const MOCK_PLANS = [
  { name: "Starter", price: 99, orgCount: 18, color: "#9499ad" },
  { name: "Growth", price: 299, orgCount: 34, color: "#6d4dff" },
  { name: "Enterprise", price: 899, orgCount: 11, color: "#2bb8c4" },
];

const MOCK_ACTIVITY = [
  { icon: "👤", text: "Jordan Lee (Acme Corp) signed in", time: "2h ago" },
  { icon: "💳", text: "Nimbus Retail upgraded to Growth", time: "6h ago" },
  { icon: "🔌", text: "Snowflake provider reconnected", time: "1d ago" },
  { icon: "⛔", text: "FinTrail admin account suspended", time: "13d ago" },
];

export function PlatformOverviewPage() {
  const { data: orgs } = useOrganizations();

  const now = new Date();
  const newThisMonth = (orgs ?? []).filter((o) => {
    const d = new Date(o.createdAt);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }).length;
  const totalUsers = (orgs ?? []).reduce((sum, o) => sum + o._count.users, 0);
  const planTotal = MOCK_PLANS.reduce((sum, p) => sum + p.price * p.orgCount, 0);

  return (
    <div className="mx-auto max-w-[1080px] p-8">
      <PageHeader title="Platform overview" sub="Revenue, growth and account health across every organization" />

      <div className="mb-5 grid grid-cols-4 gap-4">
        <KpiCard label={MOCK_MRR.label} value={MOCK_MRR.value} trend={MOCK_MRR.trend} />
        <KpiCard label="ACTIVE ORGANIZATIONS" value={String(orgs?.length ?? 0)} trend={`↑ ${newThisMonth} new this month`} />
        <KpiCard label="TOTAL USERS" value={totalUsers.toLocaleString()} />
        <KpiCard label={MOCK_CHURN.label} value={MOCK_CHURN.value} trend={MOCK_CHURN.trend} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-bold">Revenue by plan</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3.5">
            {MOCK_PLANS.map((p) => {
              const val = p.price * p.orgCount;
              const pct = Math.round((val / planTotal) * 100);
              return (
                <div key={p.name}>
                  <div className="mb-1.5 flex justify-between text-[12.5px] font-bold">
                    <span>{p.name}</span>
                    <span>
                      ${val.toLocaleString()} · {pct}%
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[#eceaf8]">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: p.color }} />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-bold">Recent admin activity</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3.5">
            {MOCK_ACTIVITY.map((a) => (
              <div key={a.text} className="flex items-start gap-2.5">
                <span className="text-[15px]">{a.icon}</span>
                <div>
                  <div className="text-[12.5px] font-semibold">{a.text}</div>
                  <div className="text-[11px] text-[#9499ad]">{a.time}</div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function KpiCard({ label, value, trend }: { label: string; value: string; trend?: string }) {
  return (
    <Card>
      <CardContent>
        <div className="mb-2 font-mono text-[10.5px] font-semibold tracking-[.06em] text-[#9499ad]">{label}</div>
        <div className="text-2xl font-extrabold">{value}</div>
        {trend && <div className="mt-1.5 text-[11.5px] font-bold text-[#1a9d6c]">{trend}</div>}
      </CardContent>
    </Card>
  );
}
```

- [x] **Step 2: Wire the route** (already included in Task 1's `App.tsx` edit above).

- [x] **Step 3: Typecheck** — clean.

- [x] **Step 4: Manually verify** — confirmed via browser: 4 stat tiles render (MRR $284,900; Active Organizations correctly showing the real count — 1 — with a real "1 new this month" trend once the `useOrganizations()` query has resolved; Total Users correctly showing the real count — 4 — with no trend line; Churn Rate 1.8%); "Revenue by plan" shows three rows summing to 100%; "Recent admin activity" shows the 4 static entries. (Note: on a cold page load before the org-list query resolves, Active Organizations/Total Users briefly show 0 — same loading-state behavior as the existing Organizations page, not a regression.)

- [ ] **Step 5: Commit** (not yet done)

---

### Task 3: `ComingSoonPage` — placeholder for Subscription plans / Providers (shadcn `Card`)

**Files:**
- Create: `web/src/routes/platform-admin/ComingSoonPage.tsx`

**Interfaces:**
- Consumes: `Card`, `CardContent` from `web/src/components/shadcn-ui/ui/card.tsx`.
- Produces: `ComingSoonPage({ title }: { title: string })`.

- [x] **Step 1: Create the placeholder page**

```tsx
import { Card, CardContent } from "../../components/shadcn-ui/ui/card";

export function ComingSoonPage({ title }: { title: string }) {
  return (
    <div className="mx-auto max-w-[1080px] p-8">
      <h1 className="text-xl font-extrabold">{title}</h1>
      <Card className="mt-10">
        <CardContent className="py-10 text-center text-[13.5px] text-[#9499ad]">
          {title} isn't built yet — coming in a future update.
        </CardContent>
      </Card>
    </div>
  );
}
```

- [x] **Step 2: Wire the two routes** (already included in Task 1's `App.tsx` edit above).

- [x] **Step 3: Typecheck** — clean.

- [x] **Step 4: Manually verify** — confirmed via browser: "Subscription plans" nav highlights, page shows title + coming-soon message inside a card. "Providers" behaves the same.

- [ ] **Step 5: Commit** (not yet done)

---

## Self-Review Notes

- **Spec coverage:** Shell + sign-out fix (Task 1), Dashboard with real Active Orgs/Total Users + mock MRR/Churn/revenue-by-plan/activity (Task 2), nav completeness via placeholders (Task 3) — all covered. Sub-projects 2-4 are explicitly out of scope per the spec and not tasked here.
- **Placeholder scan:** No TBD/TODO; every step has literal code. `ComingSoonPage`'s "isn't built yet" text is intentional UI copy, not a plan placeholder.
- **Type consistency:** `Organization._count.users` matches the field already added to `web/src/api/platformAdmin.ts`. `useAuth()`'s `user`/`logout` match `web/src/stores/useAuthStore.ts`'s actual exports. `PlatformAdminShell`, `PlatformOverviewPage`, `ComingSoonPage` names are used identically between their creation and their `App.tsx` wiring.
- **Deviation from original plan (recorded for transparency):** the original version of this plan used the app's existing inline-style/CSS-variable system throughout, matching every other page in the codebase. Mid-execution, the user asked to use shadcn/ui components with context7-verified guidance instead, scoped to the new platform-admin files only (not retrofitted onto the already-shipped `OrganizationsPage`/`OrgUsersPage`). This plan document was rewritten to match what was actually built after that decision — see Task 0.
