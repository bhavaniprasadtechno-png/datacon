# Platform Admin Shell + Dashboard (Sub-project 1 of 4)

## Problem

The platform-admin area has no navigation chrome at all: `/platform-admin/organizations` and `/platform-admin/organizations/:orgId/users` render directly with no wrapping shell, so there is no sidebar, no profile, and critically **no sign-out button** — a platform admin who logs in has no way to log out (found while verifying [[2026-07-24-platform-admin-dashboard-design]] in the browser). Separately, the user supplied a Claude Design mockup (`claude.ai/design/p/9e74661c-f4b4-4a22-b1d9-469772551a21`, file `Datacon.dc.html`) showing a complete "Datacon Super Admin" console: a dark sidebar shell with 4 sections (Dashboard, Admin users, Subscription plans, Providers) and a "Platform overview" dashboard with KPI tiles, a revenue-by-plan breakdown, and a recent-activity feed.

That full console is four independent sub-projects — a billing/plans domain, a provider-config domain, and a cross-org admin-suspend flow don't exist in the schema today, and building all four in one pass would be too large for one spec. This is sub-project 1: the shell (which fixes the logout bug immediately) and the Dashboard page, wired to real data where real data exists and explicit mock values where it doesn't (per user decision — MRR/churn/revenue-by-plan/activity have no backing data model and are out of scope for this sub-project).

Sub-projects 2-4 (Admin users redesign, Subscription plans, Providers) are separate specs, built one at a time after this one ships.

## Source of truth

The mockup (`Datacon.dc.html` in the Claude Design project) is a working prototype with real mock data in its JS state, not just static images. Exact values/colors below are pulled directly from that source, not eyeballed from screenshots:

- Sidebar bg `#1a1730`, width 236px, padding `20px 14px`.
- Nav active: white text, weight 700, bg `rgba(255,255,255,.1)`. Nav inactive: `#b7b2dd`, weight 500, transparent bg.
- "SUPER ADMIN" tag: `font: 600 9.5px 'IBM Plex Mono', monospace; letter-spacing: .12em; color: #8f89c2`.
- Logo box: 34×34, radius 10, `background: linear-gradient(135deg,#6d4dff,#2bb8c4)` — identical to this app's existing `--ac-logo` token.
- Nav items (id, label, emoji icon): `['dashboard','Dashboard','📊']`, `['admins','Admin users','👤']`, `['plans','Subscription plans','💳']`, `['providers','Providers','🔌']`.
- KPI tiles (`saKpis`): `{label: 'MONTHLY RECURRING REVENUE', value: '$284,900', trend: '↑ 12.4% vs last month', trendColor: '#1a9d6c'}`, `{label: 'ACTIVE ORGANIZATIONS', value: '63', trend: '↑ 4 new this month', trendColor: '#1a9d6c'}`, `{label: 'TOTAL USERS', value: '1,942', trend: '↑ 8.1% growth', trendColor: '#1a9d6c'}`, `{label: 'CHURN RATE', value: '1.8%', trend: '↓ 0.3pt improved', trendColor: '#1a9d6c'}`.
- Revenue-by-plan colors: starter `#9499ad`, growth `#6d4dff`, enterprise `#2bb8c4`. Mock plan data: Starter $99×18 orgs, Growth $299×34 orgs, Enterprise $899×11 orgs (percentages computed from these).
- Activity feed (`saActivity`, all static mock): `👤 Jordan Lee (Acme Corp) signed in · 2h ago`, `💳 Nimbus Retail upgraded to Growth · 6h ago`, `🔌 Snowflake provider reconnected · 1d ago`, `⛔ FinTrail admin account suspended · 13d ago`.

## Decisions from brainstorming

1. **Visual identity supersedes the earlier decision.** The original platform-admin redesign spec ([[2026-07-24-platform-admin-dashboard-design]]) chose "same look as rest of app." The user has since supplied a concrete mockup with a distinct dark-sidebar identity and asked to match it exactly ("need everything as it is") — this supersedes that earlier choice for anything under the new shell.
2. **Nav for unbuilt sections**: show all 4 nav items now (matches the mockup visually). "Admin users" routes to the existing (already-built) workspaces list page, relabeled. "Subscription plans" and "Providers" route to a shared placeholder page until their own sub-projects land.
3. **Real vs. mock data**: Active Organizations (value + trend) and Total Users (value only) use real data via the existing `useOrganizations()` hook. MRR, Churn Rate, revenue-by-plan, and the activity feed are hardcoded mock values matching the source file exactly — no new backend endpoints, no fabricated trend for Total Users specifically (no historical snapshot exists to compute "+8.1% growth" honestly, so that one tile omits its trend line rather than invent a number).

## Scope

In scope:
- `web/src/components/shell/PlatformAdminShell.tsx` (new): dark sidebar + `<Outlet/>`, matching `AppShell`'s pattern.
- `web/src/routes/platform-admin/PlatformOverviewPage.tsx` (new): the Dashboard page described above.
- `web/src/routes/platform-admin/ComingSoonPage.tsx` (new): tiny shared placeholder, takes a `title` prop, used for Subscription plans and Providers until sub-projects 3-4 land.
- `web/src/App.tsx`: nest all `/platform-admin/*` routes under the new shell; add `/platform-admin/dashboard`, `/platform-admin/plans`, `/platform-admin/providers` routes; redirect bare `/platform-admin` to `/platform-admin/dashboard`.

Out of scope (deferred to their own specs):
- Sub-project 2: redesigning "Admin users" into the cross-org admin table with suspend/activate (the mockup's `saAdmins`/`saAdminRows` — needs a real suspend concept on `User` plus an auth-enforcement change).
- Sub-project 3: "Subscription plans" CRUD (needs a real `Plan`/`Subscription` schema — the mockup's `saPlans`).
- Sub-project 4: "Providers" management (needs a way to persist/switch active LLM/infra providers that the `ai/` service actually reads — the mockup's `saProviders`).
- Any real billing/audit-log system to back the Dashboard's mock tiles/feed.

## Testing

No frontend component tests exist elsewhere in `web/` (confirmed during the original spec's research) — verification here is `tsc --noEmit` plus a manual browser walkthrough logged in as the seeded platform admin (`platform-admin@datacon.internal`, seed password in `packages/prisma/seed.ts`): confirm the sidebar renders on all platform-admin routes, Sign out actually logs out, nav highlights the active section, Admin users/Subscription plans/Providers routes render something (existing page or placeholder), and the Dashboard's real tiles match the live org/user counts while mock tiles match the source values above.
