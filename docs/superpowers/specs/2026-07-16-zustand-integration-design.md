# Design Spec: Zustand Integration & Context API Elimination

This document specifies the migration of the application's global states from traditional React Context API (`AuthContext`, `ThemeContext`, `ToastContext`, and `ConfirmContext`) to **Zustand** stores. This refactoring will simplify the component hierarchy, eliminate unnecessary context re-renders, and allow cleaner store interactions.

## Proposed Changes

We will create four Zustand stores under a new directory `app/web/src/stores/`. Consuming hooks will be rewritten to interface with these stores, maintaining backward compatibility where possible to limit changes in UI files.

### 1. Store Architectures

#### Auth Store (`app/web/src/stores/useAuthStore.ts`)
We will move authentication state out of `AuthContext` and React Query's `["me"]` hook into a self-contained Zustand store.
* **State & Types:**
  ```typescript
  import { create } from "zustand";
  import { capsFromPermissions, type Capabilities } from "@datacon/shared-types";
  import type { CurrentUser } from "../lib/types";
  import { api } from "../api/client";
  import { queryClient } from "../lib/queryClient";

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
  ```
* **Behavior:**
  * Initial state: `isLoading` is `true`, `user` is `undefined`, and `isAuthenticated` is `false`.
  * `fetchUser` performs a `GET /auth/me`. On success, it sets `user`, derives capabilities via `capsFromPermissions`, and updates status flags. On failure, it clears state.
  * `logout` calls `POST /auth/logout`, clears state, and invokes `queryClient.clear()` to purge cached TanStack Query data.

#### Theme Store (`app/web/src/stores/useThemeStore.ts`)
We will replace `ThemeContext` with a reactive Zustand store.
* **State & Types:**
  ```typescript
  import { create } from "zustand";
  import { DEFAULT_CUSTOM_ACCENT, DEFAULT_THEME_ID, THEME_PRESETS, type ThemePreset } from "@datacon/shared-types";

  type ThemeId = ThemePreset["id"] | "custom";

  interface ThemeState {
    themeId: ThemeId;
    customAccent: string;
    setTheme: (id: ThemeId) => void;
    setCustomAccent: (hex: string) => void;
  }
  ```
* **Reactive Side-Effects:**
  We use the out-of-render-loop `subscribe` method of the Zustand store to automatically update the DOM stylesheet and sync local storage:
  ```typescript
  useThemeStore.subscribe((state) => {
    const root = document.documentElement;
    root.classList.remove("dc-theme-soft", "dc-theme-emerald", "dc-theme-sapphire", "dc-theme-sunset", "dc-theme-custom");
    root.classList.add("dc-theme", `dc-theme-${state.themeId}`);
    if (state.themeId === "custom") {
      root.style.setProperty("--ac", state.customAccent);
    } else {
      root.style.removeProperty("--ac");
    }
    localStorage.setItem("datacon:theme", state.themeId);
    localStorage.setItem("datacon:customAccent", state.customAccent);
  });
  ```

#### Toast Store (`app/web/src/stores/useToastStore.ts`)
Transients alerts will be managed via a simple array store.
* **State & Types:**
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
  ```
* **Behavior:**
  * `addToast` generates a unique ID, appends the toast to `toasts`, and registers a `setTimeout` to call `dismiss` after 5.2 seconds.

#### Confirm Store (`app/web/src/stores/useConfirmStore.ts`)
Global confirmation dialog prompt state:
* **State & Types:**
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
  ```
* **Behavior:**
  * `confirm` returns a Promise that is stored in the state (`resolve` handler).
  * UI renders the confirmation modal if `pending` is non-null. When the user interacts, we call `resolve(ok)` which fires the promise resolver and clears the state.

---

### 2. UI Overlay and Layout Replacements

1. **Delete Context Files:**
   * `app/web/src/auth/AuthContext.tsx`
   * `app/web/src/theme/ThemeContext.tsx`
   * `app/web/src/components/ui/ToastContext.tsx`
   * `app/web/src/components/ui/ConfirmContext.tsx`

2. **Refactor Hooks for Seamless Transition:**
   We will create compatibility layers or direct exports from the stores so that existing hook invocations (`useAuth()`, `useTheme()`, `useToast()`, `useConfirm()`) continue working out of the box with zero change to calling UI files:
   * Create `app/web/src/auth/useAuth.ts` exporting a hook that selects state from `useAuthStore`.
   * Create `app/web/src/theme/useTheme.ts` selecting from `useThemeStore`.
   * Create `app/web/src/components/ui/useToast.ts` selecting from `useToastStore`.
   * Create `app/web/src/components/ui/useConfirm.ts` selecting from `useConfirmStore`.

3. **Host Component Overlay Mounting:**
   * The Toast display component `ToastHost.tsx` will read directly from `useToastStore`.
   * A new `ConfirmHost.tsx` component will be created to read from `useConfirmStore` and render the modal.
   * Both `ToastHost` and `ConfirmHost` will be rendered side-by-side in `AppShell.tsx`.

4. **Initialize Stores on Startup:**
   * In the main entry component, we will invoke `useAuthStore.getState().fetchUser()` to trigger the session check on mount.
   * We will run `useThemeStore.getState()` initializer logic to apply stored theme styles.

---

## Verification Plan

### Automated Verification
* We will verify the project compiles without TypeScript errors:
  ```bash
  npm run build
  ```

### Manual Verification
* Ensure login/logout works correctly and updates user state.
* Verify clicking "Add Connector" and "Remove Connector" prompts the confirmation modal (rendered via the new `ConfirmHost`) and that selecting options resolves correctly.
* Verify adding/saving database configurations fires Toast notifications.
* Verify switching theme accents updates the document styles instantly.
