# Disable Forecasts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Comment out all imports, routes, and sidebar navigation items for the Forecasts page to hide it from the user interface while keeping the code files for future use.

**Architecture:** Comment out the nav item in `Sidebar.tsx` and the corresponding route registration and import in `App.tsx`.

**Tech Stack:** React, React Router, TypeScript.

---

### Task 1: Comment out Forecasts in Sidebar Navigation

**Files:**
- Modify: `app/web/src/components/shell/Sidebar.tsx`

- [ ] **Step 1: Comment out the `forecasts` object in the `NAV` array**

Modify [Sidebar.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/components/shell/Sidebar.tsx) to comment out the forecasts line:

```tsx
const NAV: NavDef[] = [
  { id: "chat", icon: <MessageSquare size={16} />, label: "Chat", to: "/chat/history" },
  { id: "insights", icon: <TrendingUp size={16} />, label: "Insights", to: "/insights" },
  { id: "connectors", icon: <Plug size={16} />, label: "Connectors", to: "/connectors" },
  { id: "documents", icon: <Database size={16} />, label: "Data Sources", to: "/data-sources" },
  // { id: "forecasts", icon: <LineChart size={16} />, label: "Forecasts", to: "/forecasts" },
  { id: "settings", icon: <Settings size={16} />, label: "User management", to: "/settings/users" },
  { id: "themes", icon: <Palette size={16} />, label: "Themes", to: "/themes", divider: true },
];
```

---

### Task 2: Comment out Forecasts Route and Import in App.tsx

**Files:**
- Modify: `app/web/src/App.tsx`

- [ ] **Step 1: Comment out the `ForecastsPage` import and route registration**

Modify [App.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/App.tsx):

Comment out the import:
```tsx
// import { ForecastsPage } from "./routes/forecasts/ForecastsPage";
```

Comment out the route element:
```tsx
        {/* <Route path="/forecasts" element={<ForecastsPage />} /> */}
```

---

### Task 3: Compilation and Build Verification

- [ ] **Step 1: Run production build**

Run command in `app/web`:
```bash
npm run build
```
Expected output: Successful build with zero errors.
