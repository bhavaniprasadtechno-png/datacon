# UI Polish (Shadcn-style & Icon Library Integration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Datacon app to use a professional shadcn-style neutral design (Slate/Zinc), replace all emojis with Lucide React icons, and align all typography and corners to design specs.

**Architecture:** We will define clean Slate-based design variables in `tokens.css` that map existing variables to our new design specs, then update the Button, Sidebar, ChatPage, and AgentVisualization components to consume them and render Lucide icons.

**Tech Stack:** React, TypeScript, Vite, Lucide React, Vanilla CSS.

---

### Task 1: CSS Design Tokens & Theme Setup

**Files:**
- Modify: `app/web/src/styles/tokens.css`
- Modify: `app/packages/shared-types/src/themes.ts`

- [ ] **Step 1: Update design tokens in `tokens.css`**
  Open [tokens.css](file:///c:/Users/pc/Desktop/datacon/app/web/src/styles/tokens.css) and replace the top section and root variables with:
  ```css
  @import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap");

  * {
    box-sizing: border-box;
  }
  html,
  body,
  #root {
    margin: 0;
    height: 100%;
  }
  body {
    background: var(--ac-bg);
    font-family: "Inter", -apple-system, system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    color: var(--ac-fg);
  }
  input,
  button,
  textarea,
  select {
    font-family: inherit;
  }
  button {
    cursor: pointer;
    border: none;
    background: none;
  }
  ::-webkit-scrollbar {
    width: 10px;
    height: 10px;
  }
  ::-webkit-scrollbar-thumb {
    background: var(--ac-border);
    border-radius: 6px;
    border: 3px solid transparent;
    background-clip: content-box;
  }
  ::-webkit-scrollbar-thumb:hover {
    background: #bfc3d4;
    background-clip: content-box;
  }

  /* ── Theme tokens — ported verbatim from project/Datacon.dc.html ── */
  :root {
    --ac-bg: #ffffff;
    --ac-bg-muted: #fafafa;
    --ac-fg: #09090b;
    --ac-muted: #71717a;
    --ac-border: #e4e4e7;
    
    --ac: #0052ff;
    --ac2: #003ecc;
    --ac-deep: #002db3;
    --ac-soft: #e6efff;
    --ac-softer: #f5f8ff;
    --ac-ring: #a8c7ff;
    
    --ac-grad: linear-gradient(135deg, #0052ff, #0052ff);
    --ac-logo: linear-gradient(135deg, #0052ff, #0052ff);

    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --radius-xl: 24px;
    --radius-pill: 9999px;
  }
  .dc-theme {
    --ac-soft: color-mix(in srgb, var(--ac) 13%, white);
    --ac-softer: color-mix(in srgb, var(--ac) 6%, white);
    --ac-ring: color-mix(in srgb, var(--ac) 34%, white);
    --ac-bg: #ffffff;
    --ac-bg-muted: #fafafa;
    --ac-fg: #09090b;
    --ac-muted: #71717a;
    --ac-border: #e4e4e7;
    --ac-grad: linear-gradient(135deg, var(--ac), var(--ac));
  }
  .dc-theme-soft {
    --ac: #0052ff;
    --ac2: #003ecc;
    --ac-deep: #002db3;
    --ac-logo: linear-gradient(135deg, #0052ff, #0052ff);
  }
  .dc-theme-emerald {
    --ac: #0f9d6b;
    --ac2: #17b884;
    --ac-deep: #0b7d54;
    --ac-logo: linear-gradient(135deg, #0f9d6b, #12b6a6);
  }
  .dc-theme-sapphire {
    --ac: #0052ff;
    --ac2: #003ecc;
    --ac-deep: #002db3;
    --ac-logo: linear-gradient(135deg, #0052ff, #0052ff);
  }
  .dc-theme-sunset {
    --ac: #e2544f;
    --ac2: #f0725c;
    --ac-deep: #c53c50;
    --ac-logo: linear-gradient(135deg, #e2544f, #f0a24a);
  }
  ```

- [ ] **Step 2: Update theme presets in `themes.ts`**
  Open [themes.ts](file:///c:/Users/pc/Desktop/datacon/app/packages/shared-types/src/themes.ts) and modify `THEME_PRESETS`:
  ```typescript
  export const THEME_PRESETS: ThemePreset[] = [
    { id: "soft", name: "Coinbase Premium", description: "Quietly-confident institutional blue", ac: "#0052ff", ac2: "#003ecc", tint: "#e6efff" },
    { id: "emerald", name: "Emerald Lux", description: "Deep green · jade", ac: "#0f9d6b", ac2: "#17b884", tint: "#e3f6ee" },
    { id: "sapphire", name: "Sapphire Blue", description: "Royal blue · cyan", ac: "#0052ff", ac2: "#003ecc", tint: "#e6efff" },
    { id: "sunset", name: "Sunset Coral", description: "Warm coral · amber", ac: "#e2544f", ac2: "#f0725c", tint: "#fdeaec" },
  ];

  export const DEFAULT_THEME_ID = "soft";
  export const DEFAULT_CUSTOM_ACCENT = "#0052ff";
  ```

- [ ] **Step 3: Compile shared-types workspace**
  Run: `npm run build --workspace=packages/shared-types`
  Expected: SUCCESS

---

### Task 2: Polishing the Button Component

**Files:**
- Modify: `app/web/src/components/ui/Button.tsx`

- [ ] **Step 1: Restyle `Button.tsx`**
  Open [Button.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/components/ui/Button.tsx) and change the styling properties:
  ```typescript
  const base: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    fontSize: 13.5,
    fontWeight: 500,
    borderRadius: "var(--radius-md)",
    padding: "8px 16px",
    transition: "filter .12s, background .12s, border-color .12s",
  };

  const variants: Record<Variant, React.CSSProperties> = {
    primary: {
      background: "var(--ac)",
      color: "#fff",
    },
    danger: {
      background: "#cf202f",
      color: "#fff",
    },
    secondary: {
      background: "var(--ac-bg-muted)",
      color: "var(--ac-fg)",
      border: "1px solid var(--ac-border)",
    },
    ghost: {
      background: "transparent",
      color: "var(--ac-muted)",
    },
  };
  ```

- [ ] **Step 2: Verify type-checking in `web` workspace**
  Run: `npx tsc --noEmit` in `app/web`
  Expected: SUCCESS (no errors)

---

### Task 3: Refactoring the Sidebar Component with Lucide Icons

**Files:**
- Modify: `app/web/src/components/shell/Sidebar.tsx`

- [ ] **Step 1: Add Lucide imports and update `NAV` definition**
  Open [Sidebar.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/components/shell/Sidebar.tsx). Add Lucide imports:
  ```typescript
  import {
    MessageSquare,
    TrendingUp,
    Plug,
    Database,
    LineChart,
    Settings,
    Palette,
    User,
    Shield,
    Link as LinkIcon,
    Key,
    ChevronLeft,
    ChevronRight,
    LogOut,
    X,
    Mail,
    Clock,
    Sparkles
  } from "lucide-react";
  ```
  Replace `NAV` and `SUB_NAV` definitions:
  ```typescript
  interface NavDef {
    id: string;
    icon: React.ReactNode;
    label: string;
    to: string;
    divider?: boolean;
  }

  const NAV = (activeId: string): NavDef[] => [
    { id: "chat", icon: <MessageSquare size={16} />, label: "Chat", to: "/chat/history" },
    { id: "insights", icon: <TrendingUp size={16} />, label: "Insights", to: "/insights" },
    { id: "connectors", icon: <Plug size={16} />, label: "Connectors", to: "/connectors" },
    { id: "documents", icon: <Database size={16} />, label: "Data Sources", to: "/data-sources" },
    { id: "forecasts", icon: <LineChart size={16} />, label: "Forecasts", to: "/forecasts" },
    { id: "settings", icon: <Settings size={16} />, label: "User management", to: "/settings/users" },
    { id: "themes", icon: <Palette size={16} />, label: "Themes", to: "/themes", divider: true },
  ];

  const SUB_NAV = [
    { id: "users", icon: <User size={14} />, label: "Users", to: "/settings/users" },
    { id: "roles", icon: <Shield size={14} />, label: "Roles", to: "/settings/roles" },
    { id: "assign", icon: <LinkIcon size={14} />, label: "Assign roles", to: "/settings/assign" },
    { id: "permissions", icon: <Key size={14} />, label: "Permissions", to: "/settings/permissions" },
  ];
  ```

- [ ] **Step 2: Update Sidebar rendering block**
  Change the sidebar body layout to:
  - Remove all raw emojis and replace them with Lucide icons.
  - Sidebar container `borderRight: "1px solid var(--ac-border)"`.
  - "+ New chat" button `borderRadius: "var(--radius-md)"`.
  - Active nav links: `borderRadius: "var(--radius-sm)"`, `background: active ? "var(--ac-soft)" : "transparent"`, `color: active ? "var(--ac)" : "var(--ac-muted)"`.
  - Replace `«` / `»` collapse symbols with `<ChevronLeft size={16} />` / `<ChevronRight size={16} />`.
  - Replace `✕` with `<X size={12} />`.
  - Replace `👤 Profile` and `⎋ Sign out` with `<User size={14} /> Profile` and `<LogOut size={14} /> Sign out`.
  - Replace `InfoRow` icons in ProfileModal: `✉️` → `<Mail size={16} />`, `🛡️` → `<Shield size={16} />`, `🕑` → `<Clock size={16} />`.

- [ ] **Step 3: Verify type-checking**
  Run: `npx tsc --noEmit` in `app/web`
  Expected: SUCCESS

---

### Task 4: Refactoring ChatPage & Suggestion Cards

**Files:**
- Modify: `app/web/src/routes/chat/ChatPage.tsx`

- [ ] **Step 1: Import Lucide icons and update suggestions layout**
  Open [ChatPage.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/routes/chat/ChatPage.tsx). Import Lucide:
  ```typescript
  import {
    Sparkles,
    ArrowUp,
    ThumbsUp,
    ThumbsDown,
    AlertCircle,
    FileText,
    Compass,
    LineChart,
    Play
  } from "lucide-react";
  ```
  Replace suggestions categories with Lucide icons inside `CHAT_SUGGESTIONS` loop:
  - `descriptive` → `<FileText size={12} />`
  - `diagnostic` → `<Compass size={12} />`
  - `predictive` → `<LineChart size={12} />`
  - `prescriptive` → `<Play size={12} />`
  - Use `borderRadius: "var(--radius-lg)"` (12px), `border: "1px solid var(--ac-border)"` for suggestion cards.

- [ ] **Step 2: Update Chat Bubbles, Model Selector, and Composer**
  - Model selector select: `border: "1px solid var(--ac-border)"`, `borderRadius: "var(--radius-md)"`, `background: "#fff"`, `color: "var(--ac-fg)"`.
  - Empty state logo: Replace `✦` with `<Sparkles size={24} style={{ color: "var(--ac)" }} />`.
  - User message: `borderRadius: "var(--radius-lg) var(--radius-lg) 0 var(--radius-lg)"`, `background: "var(--ac)"`, `color: "#fff"`.
  - Agent message: `borderRadius: "0 var(--radius-lg) var(--radius-lg) var(--radius-lg)"`, `border: "1px solid var(--ac-border)"`, `background: "#fff"`, `padding: "20px"`.
  - Upvote/Downvote buttons: Replace `▲ Helpful` / `▼` with `<ThumbsUp size={12} /> Helpful` and `<ThumbsDown size={12} />`.
  - Input form: `borderRadius: "var(--radius-md)"` (8px), `border: "1px solid var(--ac-border)"`.
  - Submit button: Replace `Ask ✦` with a circular plate containing `<ArrowUp size={14} />` or a clean primary button style.

- [ ] **Step 3: Verify type-checking**
  Run: `npx tsc --noEmit` in `app/web`
  Expected: SUCCESS

---

### Task 5: Refactoring Agent Visualization

**Files:**
- Modify: `app/web/src/routes/chat/AgentVisualization.tsx`

- [ ] **Step 1: Update styles and layout**
  Open [AgentVisualization.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/routes/chat/AgentVisualization.tsx).
  - Diagnostic sources: Set citation card left border to `2px solid var(--ac)`, background `#fafafa`, `borderRadius: "var(--radius-sm)"`.
  - Predictive SVG: Chart polyline stroke `var(--ac)`. Container uses `borderRadius: "var(--radius-lg)"`, border `1px solid var(--ac-border)`, background `#ffffff`.
  - Prescriptive Action Table: Outer container `border: "1px solid var(--ac-border)"`, `borderRadius: "var(--radius-lg)"`. Header uses `background: "var(--ac-bg-muted)"`, font `JetBrains Mono`.

- [ ] **Step 2: Compile the workspace**
  Run: `npm run build` in `app/`
  Expected: SUCCESS
