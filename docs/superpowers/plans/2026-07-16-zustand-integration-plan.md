# Zustand Integration & Context API Elimination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace React Contexts (`AuthContext`, `ThemeContext`, `ToastContext`, `ConfirmContext`) with Zustand stores and eliminate nested context providers in `App.tsx`.

**Architecture:** Create individual Zustand stores for Auth, Theme, Toast, and Confirm. Refactor existing context files to act as thin compatibility hook exports to avoid changing import statements in UI components. Render Toast and Confirm overlays from the global `AppShell`.

**Tech Stack:** Zustand, React 19, Vite, TypeScript, Axios, TanStack React Query

---

## Proposed Changes

### Task 1: Install Zustand & Setup Shared QueryClient

**Files:**
- Modify: `app/web/package.json`
- Create: `app/web/src/lib/queryClient.ts`

- [x] **Step 1: Install zustand dependency**
  Run: `npm install zustand` in `c:/Users/pc/Desktop/datacon/app/web`
  Expected: Installation completes, `zustand` added to `package.json`.

- [x] **Step 2: Create queryClient.ts**
  Create [queryClient.ts](file:///C:/Users/pc/Desktop/datacon/app/web/src/lib/queryClient.ts):
  ```typescript
  import { QueryClient } from "@tanstack/react-query";
  export const queryClient = new QueryClient();
  ```

---

### Task 2: Create Zustand Stores

**Files:**
- Create: `app/web/src/stores/useAuthStore.ts`
- Create: `app/web/src/stores/useThemeStore.ts`
- Create: `app/web/src/stores/useToastStore.ts`
- Create: `app/web/src/stores/useConfirmStore.ts`

- [x] **Step 1: Create useAuthStore.ts**
  Create [useAuthStore.ts](file:///C:/Users/pc/Desktop/datacon/app/web/src/stores/useAuthStore.ts):
  ```typescript
  import { create } from "zustand";
  import { capsFromPermissions, type Capabilities } from "@datacon/shared-types";
  import type { CurrentUser } from "../lib/types";
  import { api } from "../api/client";
  import { queryClient } from "../lib/queryClient";

  const EMPTY_CAPS = capsFromPermissions([]);

  interface AuthState {
    user: CurrentUser | undefined;
    caps: Capabilities;
    isLoading: boolean;
    isAuthenticated: boolean;
    fetchUser: () => Promise<void>;
    login: (email: string, password: string) => Promise<void>;
    register: (name: string, email: string, password: string) => Promise<void>;
    quickLogin: (personaId: string) => Promise<void>;
    logout: () => Promise<void>;
  }

  export const useAuthStore = create<AuthState>((set, get) => ({
    user: undefined,
    caps: EMPTY_CAPS,
    isLoading: true,
    isAuthenticated: false,
    fetchUser: async () => {
      try {
        const res = await api.get<CurrentUser>("/auth/me");
        set({
          user: res.data,
          caps: capsFromPermissions(res.data.permissions),
          isAuthenticated: true,
          isLoading: false,
        });
      } catch {
        set({
          user: undefined,
          caps: EMPTY_CAPS,
          isAuthenticated: false,
          isLoading: false,
        });
      }
    },
    login: async (email, password) => {
      await api.post("/auth/login", { email, password });
      await get().fetchUser();
    },
    register: async (name, email, password) => {
      await api.post("/auth/register", { name, email, password });
      await get().fetchUser();
    },
    quickLogin: async (personaId) => {
      await api.post("/auth/quick-login", { personaId });
      await get().fetchUser();
    },
    logout: async () => {
      await api.post("/auth/logout");
      set({
        user: undefined,
        caps: EMPTY_CAPS,
        isAuthenticated: false,
      });
      queryClient.clear();
    },
  }));
  ```

- [x] **Step 2: Create useThemeStore.ts**
  Create [useThemeStore.ts](file:///C:/Users/pc/Desktop/datacon/app/web/src/stores/useThemeStore.ts):
  ```typescript
  import { create } from "zustand";
  import { DEFAULT_CUSTOM_ACCENT, DEFAULT_THEME_ID, type ThemePreset } from "@datacon/shared-types";

  type ThemeId = ThemePreset["id"] | "custom";

  interface ThemeState {
    themeId: ThemeId;
    customAccent: string;
    setTheme: (id: ThemeId) => void;
    setCustomAccent: (hex: string) => void;
    initialize: () => void;
  }

  const STORAGE_THEME = "datacon:theme";
  const STORAGE_CUSTOM = "datacon:customAccent";

  export const useThemeStore = create<ThemeState>((set) => ({
    themeId: (localStorage.getItem(STORAGE_THEME) as ThemeId) || DEFAULT_THEME_ID,
    customAccent: localStorage.getItem(STORAGE_CUSTOM) || DEFAULT_CUSTOM_ACCENT,
    setTheme: (id) => set({ themeId: id }),
    setCustomAccent: (hex) => set({ customAccent: hex, themeId: "custom" }),
    initialize: () => {
      const state = useThemeStore.getState();
      applyTheme(state.themeId, state.customAccent);
    },
  }));

  function applyTheme(themeId: ThemeId, customAccent: string) {
    const root = document.documentElement;
    root.classList.remove("dc-theme-soft", "dc-theme-emerald", "dc-theme-sapphire", "dc-theme-sunset", "dc-theme-custom");
    root.classList.add("dc-theme", `dc-theme-${themeId}`);
    if (themeId === "custom") {
      root.style.setProperty("--ac", customAccent);
    } else {
      root.style.removeProperty("--ac");
    }
    localStorage.setItem(STORAGE_THEME, themeId);
    localStorage.setItem(STORAGE_CUSTOM, customAccent);
  }

  useThemeStore.subscribe((state) => {
    applyTheme(state.themeId, state.customAccent);
  });
  ```

- [x] **Step 3: Create useToastStore.ts**
  Create [useToastStore.ts](file:///C:/Users/pc/Desktop/datacon/app/web/src/stores/useToastStore.ts):
  ```typescript
  import { create } from "zustand";
  import type { ReactNode } from "react";

  export interface ToastSpec {
    icon: ReactNode;
    accent: string;
    title: string;
    desc: string;
  }

  export interface Toast extends ToastSpec {
    id: number;
  }

  interface ToastState {
    toasts: Toast[];
    addToast: (spec: ToastSpec) => void;
    dismiss: (id: number) => void;
  }

  let seq = 1;
  const AUTO_DISMISS_MS = 5200;

  export const useToastStore = create<ToastState>((set, get) => ({
    toasts: [],
    addToast: (spec) => {
      const id = seq++;
      set((state) => ({ toasts: [...state.toasts, { ...spec, id }] }));
      setTimeout(() => get().dismiss(id), AUTO_DISMISS_MS);
    },
    dismiss: (id) => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
    },
  }));
  ```

- [x] **Step 4: Create useConfirmStore.ts**
  Create [useConfirmStore.ts](file:///C:/Users/pc/Desktop/datacon/app/web/src/stores/useConfirmStore.ts):
  ```typescript
  import { create } from "zustand";

  export interface ConfirmSpec {
    title: string;
    body: string;
    label: string;
    tone: "primary" | "danger";
  }

  interface PendingConfirm extends ConfirmSpec {
    resolve: (ok: boolean) => void;
  }

  interface ConfirmState {
    pending: PendingConfirm | null;
    confirm: (spec: ConfirmSpec) => Promise<boolean>;
    resolve: (ok: boolean) => void;
  }

  export const useConfirmStore = create<ConfirmState>((set, get) => ({
    pending: null,
    confirm: (spec) => {
      return new Promise<boolean>((resolve) => {
        set({ pending: { ...spec, resolve } });
      });
    },
    resolve: (ok) => {
      const pending = get().pending;
      if (pending) {
        pending.resolve(ok);
      }
      set({ pending: null });
    },
  }));
  ```

---

### Task 3: Refactor Context Files to thin Hook Wrappers

**Files:**
- Modify: `app/web/src/auth/AuthContext.tsx`
- Modify: `app/web/src/theme/ThemeContext.tsx`
- Modify: `app/web/src/components/ui/ToastContext.tsx`
- Modify: `app/web/src/components/ui/ConfirmContext.tsx`

- [x] **Step 1: Rewrite AuthContext.tsx**
  Modify [AuthContext.tsx](file:///C:/Users/pc/Desktop/datacon/app/web/src/auth/AuthContext.tsx):
  ```typescript
  import { useAuthStore } from "../stores/useAuthStore";
  import type { ReactNode } from "react";

  export function useAuth() {
    const user = useAuthStore((state) => state.user);
    const caps = useAuthStore((state) => state.caps);
    const isLoading = useAuthStore((state) => state.isLoading);
    const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
    const login = useAuthStore((state) => state.login);
    const register = useAuthStore((state) => state.register);
    const quickLogin = useAuthStore((state) => state.quickLogin);
    const logout = useAuthStore((state) => state.logout);

    return {
      user,
      caps,
      isLoading,
      isAuthenticated,
      login,
      register,
      quickLogin,
      logout,
    };
  }

  export function AuthProvider({ children }: { children: ReactNode }) {
    return <>{children}</>;
  }
  ```

- [x] **Step 2: Rewrite ThemeContext.tsx**
  Modify [ThemeContext.tsx](file:///C:/Users/pc/Desktop/datacon/app/web/src/theme/ThemeContext.tsx):
  ```typescript
  import { useThemeStore } from "../stores/useThemeStore";
  import { THEME_PRESETS } from "@datacon/shared-types";
  import type { ReactNode } from "react";

  export function useTheme() {
    const themeId = useThemeStore((state) => state.themeId);
    const customAccent = useThemeStore((state) => state.customAccent);
    const setTheme = useThemeStore((state) => state.setTheme);
    const setCustomAccent = useThemeStore((state) => state.setCustomAccent);

    return { themeId, customAccent, setTheme, setCustomAccent };
  }

  export function ThemeProvider({ children }: { children: ReactNode }) {
    return <>{children}</>;
  }

  export { THEME_PRESETS };
  ```

- [x] **Step 3: Rewrite ToastContext.tsx**
  Modify [ToastContext.tsx](file:///C:/Users/pc/Desktop/datacon/app/web/src/components/ui/ToastContext.tsx):
  ```typescript
  import { useToastStore } from "../../stores/useToastStore";
  import type { ReactNode } from "react";
  export type { ToastSpec } from "../../stores/useToastStore";

  export function useToast() {
    const toasts = useToastStore((state) => state.toasts);
    const addToast = useToastStore((state) => state.addToast);
    const dismiss = useToastStore((state) => state.dismiss);

    return { toasts, addToast, dismiss };
  }

  export function ToastProvider({ children }: { children: ReactNode }) {
    return <>{children}</>;
  }
  ```

- [x] **Step 4: Rewrite ConfirmContext.tsx**
  Modify [ConfirmContext.tsx](file:///C:/Users/pc/Desktop/datacon/app/web/src/components/ui/ConfirmContext.tsx):
  ```typescript
  import { useConfirmStore } from "../../stores/useConfirmStore";
  import type { ReactNode } from "react";

  export function useConfirm() {
    const confirm = useConfirmStore((state) => state.confirm);
    return confirm;
  }

  export function ConfirmProvider({ children }: { children: ReactNode }) {
    return <>{children}</>;
  }
  ```

---

### Task 4: Setup Confirmation and Toast Host Overlays

**Files:**
- Modify: `app/web/src/components/ui/ToastHost.tsx`
- Create: `app/web/src/components/ui/ConfirmHost.tsx`
- Modify: `app/web/src/components/shell/AppShell.tsx`

- [x] **Step 1: Update ToastHost.tsx**
  Modify [ToastHost.tsx](file:///C:/Users/pc/Desktop/datacon/app/web/src/components/ui/ToastHost.tsx) to read from `useToastStore` directly:
  ```typescript
  import { useToastStore } from "../../stores/useToastStore";

  export function ToastHost() {
    const toasts = useToastStore((state) => state.toasts);
    const dismiss = useToastStore((state) => state.dismiss);

    if (toasts.length === 0) return null;
    return (
      <div style={{ position: "fixed", right: 22, bottom: 22, width: 320, display: "flex", flexDirection: "column", gap: 11, zIndex: 90 }}>
        {toasts.map((t) => (
          <div
            key={t.id}
            className="dvfu"
            style={{
              background: "#fff",
              borderRadius: 13,
              borderLeft: `3px solid ${t.accent}`,
              boxShadow: "0 2px 6px rgba(28,30,50,.05),0 16px 36px -30px rgba(28,30,50,.4)",
              padding: "12px 14px",
              display: "flex",
              gap: 10,
              alignItems: "flex-start",
              animation: "dvtoast .3s cubic-bezier(.2,.7,.3,1) both",
            }}
          >
            <div style={{ fontSize: 16, lineHeight: 1 }}>{t.icon}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#1a1d29" }}>{t.title}</div>
              <div style={{ fontSize: 11.5, color: "#71768a", marginTop: 2 }}>{t.desc}</div>
            </div>
            <button onClick={() => dismiss(t.id)} style={{ color: "#b0b4c6", fontSize: 12, padding: 2 }}>
              ✕
            </button>
          </div>
        ))}
      </div>
    );
  }
  ```

- [x] **Step 2: Create ConfirmHost.tsx**
  Create [ConfirmHost.tsx](file:///C:/Users/pc/Desktop/datacon/app/web/src/components/ui/ConfirmHost.tsx):
  ```typescript
  import { useConfirmStore } from "../../stores/useConfirmStore";
  import { Modal } from "./Modal";
  import { Button } from "./Button";

  export function ConfirmHost() {
    const pending = useConfirmStore((state) => state.pending);
    const resolve = useConfirmStore((state) => state.resolve);

    return (
      <Modal open={!!pending} onClose={() => resolve(false)} width={400} z={60}>
        {pending && (
          <>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 8 }}>{pending.title}</div>
            <div style={{ fontSize: 13, color: "#71768a", marginBottom: 20, lineHeight: 1.5 }}>{pending.body}</div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <Button variant="secondary" onClick={() => resolve(false)}>
                Cancel
              </Button>
              <Button variant={pending.tone === "danger" ? "danger" : "primary"} onClick={() => resolve(true)}>
                {pending.label}
              </Button>
            </div>
          </>
        )}
      </Modal>
    );
  }
  ```

- [x] **Step 3: Update AppShell.tsx to render overlays**
  Modify [AppShell.tsx](file:///C:/Users/pc/Desktop/datacon/app/web/src/components/shell/AppShell.tsx) to render `ConfirmHost` and `ToastHost`:
  ```typescript
  import { Outlet } from "react-router-dom";
  import { Sidebar } from "./Sidebar";
  import { ToastHost } from "../ui/ToastHost";
  import { ConfirmHost } from "../ui/ConfirmHost";

  export function AppShell() {
    return (
      <div style={{ height: "100vh", width: "100vw", display: "flex", overflow: "hidden" }}>
        <Sidebar />
        <main style={{ flex: 1, minWidth: 0, overflowY: "auto", background: "var(--ac-bg)" }}>
          <Outlet />
        </main>
        <ToastHost />
        <ConfirmHost />
      </div>
    );
  }
  ```

---

### Task 5: Clean Up App.tsx and Initialize Stores

**Files:**
- Modify: `app/web/src/App.tsx`

- [x] **Step 1: Modify App.tsx**
  Change [App.tsx](file:///C:/Users/pc/Desktop/datacon/app/web/src/App.tsx):
  ```typescript
  import { useEffect } from "react";
  import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
  import { QueryClientProvider } from "@tanstack/react-query";
  import { useAuth } from "./auth/AuthContext";
  import { AppShell } from "./components/shell/AppShell";
  import { RequireAdmin } from "./components/shell/RequireAdmin";
  import { AuthPage } from "./routes/auth/AuthPage";
  import { UsersPage } from "./routes/settings/UsersPage";
  import { RolesPage } from "./routes/settings/RolesPage";
  import { AssignRolesPage } from "./routes/settings/AssignRolesPage";
  import { PermissionsPage } from "./routes/settings/PermissionsPage";
  import { ConnectorsPage } from "./routes/connectors/ConnectorsPage";
  import { DataSourcesPage } from "./routes/data-sources/DataSourcesPage";
  import { ChatPage } from "./routes/chat/ChatPage";
  import { ChatHistoryPage } from "./routes/chat/ChatHistoryPage";
  import { ForecastsPage } from "./routes/forecasts/ForecastsPage";
  import { InsightsPage } from "./routes/insights/InsightsPage";
  import { ThemesPage } from "./routes/themes/ThemesPage";
  import { queryClient } from "./lib/queryClient";
  import { useAuthStore } from "./stores/useAuthStore";
  import { useThemeStore } from "./stores/useThemeStore";

  function RequireAuth({ children }: { children: React.ReactNode }) {
    const { isAuthenticated, isLoading } = useAuth();
    if (isLoading) return null;
    if (!isAuthenticated) return <Navigate to="/" replace />;
    return <>{children}</>;
  }

  function AppRoutes() {
    return (
      <Routes>
        <Route path="/" element={<AuthPage />} />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/history" element={<ChatHistoryPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/connectors" element={<ConnectorsPage />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
          <Route path="/forecasts" element={<ForecastsPage />} />
          <Route path="/themes" element={<ThemesPage />} />
          <Route
            path="/settings/users"
            element={
              <RequireAdmin>
                <UsersPage />
              </RequireAdmin>
            }
          />
          <Route
            path="/settings/roles"
            element={
              <RequireAdmin>
                <RolesPage />
              </RequireAdmin>
            }
          />
          <Route
            path="/settings/assign"
            element={
              <RequireAdmin>
                <AssignRolesPage />
              </RequireAdmin>
            }
          />
          <Route
            path="/settings/permissions"
            element={
              <RequireAdmin>
                <PermissionsPage />
              </RequireAdmin>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    );
  }

  export default function App() {
    useEffect(() => {
      useAuthStore.getState().fetchUser();
      useThemeStore.getState().initialize();
    }, []);

    return (
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </QueryClientProvider>
    );
  }
  ```

---

## Verification Plan

### Automated Tests
- Run `npm run build` inside `app/web` to verify everything compiles cleanly with no compiler issues.

### Manual Verification
- Start the server: `npm run dev`
- Verify theme switching works.
- Verify connector syncing triggers blinking status and auto-polling works as expected.
- Verify "Add Connector" displays the confirmation modal via `ConfirmHost` and resolves/closes on selection.
- Verify toast alerts are displayed on save or delete actions.
