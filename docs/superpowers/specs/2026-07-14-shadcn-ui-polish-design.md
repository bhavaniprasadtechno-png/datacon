# Design Spec: UI Polish (Shadcn-style & Icon Library Integration)

This design spec outlines how we will refactor the UI of the application to look like a professional, hand-crafted **shadcn/ui** interface. We will replace all emoji icons with a modern SVG icon library (`lucide-react`) and update the vanilla CSS variables, typography, layouts, and components.

## Goals
- **Clean Aesthetic:** Transition from a colorful, emoji-heavy UI to a clean, quiet neutral Slate/Zinc interface with high-contrast Coinbase Blue accents.
- **Lucide Icon Library:** Standardize all icons using `lucide-react` instead of unicode emojis or text glyphs.
- **Sleek Geometry:** Switch from bubbly, pill-shaped cards and large rounded elements to shadcn's signature `6px`-`12px` border-radii.

---

## 1. Tokens & Design System (`app/web/src/styles/tokens.css`)

We will redefine our central CSS variables to match the Slate/Zinc palette. The variables map to shadcn/ui equivalents:

```css
:root {
  /* Shadcn Slate / Zinc neutral palette */
  --ac-bg: #ffffff;             /* Main canvas background */
  --ac-bg-muted: #fafafa;       /* Muted background (sidebar, headers) */
  --ac-fg: #09090b;             /* Neutral foreground text */
  --ac-muted: #71717a;          /* Muted subtext */
  --ac-border: #e4e4e7;         /* Hairline borders (slate-200) */
  
  /* Primary Brand Accent (Coinbase Blue) */
  --ac: #0052ff;                
  --ac2: #003ecc;               
  --ac-deep: #002db3;           
  
  /* Active states & highlights */
  --ac-soft: #e6efff;           /* Active nav background, highlighted bubbles */
  --ac-softer: #f5f8ff;         
  --ac-ring: #a8c7ff;           
  
  /* Solid colors instead of gradients */
  --ac-grad: linear-gradient(135deg, #0052ff, #0052ff);
  --ac-logo: linear-gradient(135deg, #0052ff, #0052ff);

  /* Border Radii */
  --radius-sm: 6px;             /* Active items, sub-navigation */
  --radius-md: 8px;             /* Buttons, inputs, search compose wrappers */
  --radius-lg: 12px;            /* Cards, chat bubbles, modals */
  --radius-pill: 9999px;        /* Circular plates (avatars) */
}
```

---

## 2. Icon Replacements (`lucide-react`)

All emojis will be replaced with crisp Lucide React components:

### Sidebar Navigation
| Current Emoji | Target Lucide Icon |
| :--- | :--- |
| `💬 Chat` | `MessageSquare` |
| `📊 Insights` | `TrendingUp` |
| `🔌 Connectors` | `Plug` |
| `🗄️ Data Sources` | `Database` |
| `📈 Forecasts` | `LineChart` |
| `⚙️ User management` | `Settings` |
| `🎨 Themes` | `Palette` |
| `👤 Users` | `User` |
| `🛡️ Roles` | `Shield` |
| `🔗 Assign roles` | `Link` |
| `🔑 Permissions` | `Key` |
| `👤 Profile` (footer) | `User` |
| `⎋ Sign out` (footer) | `LogOut` |
| `«` / `»` (collapse) | `ChevronLeft` / `ChevronRight` |
| `✕` (delete history) | `X` |

### Chat Interface
| Current Symbol/Emoji | Target Lucide Icon |
| :--- | :--- |
| `✦` (Empty state logo) | `Sparkles` |
| `descriptive` suggestion | `FileText` |
| `diagnostic` suggestion | `Compass` |
| `predictive` suggestion | `LineChart` |
| `prescriptive` suggestion | `Play` |
| `▲ Helpful` / `▼` (voting) | `ThumbsUp` / `ThumbsDown` |
| `⚠️` (Failure toasts) | `AlertCircle` |
| `Ask ✦` (submit button) | `ArrowUp` (inside circular button) |

### Inventory & Connector pages
| Current Emoji | Target Lucide Icon |
| :--- | :--- |
| `↻ Refresh` | `RefreshCw` |
| `↑ New source` | `Upload` |
| `🔒` | `Lock` |
| `👁` | `Eye` |
| `🗑` | `Trash2` |
| `✓` (Indexed status) | `Check` |
| `◷` (Processing status) | `Loader2` (with spinning animation) |
| `✕` (Failed status) | `XCircle` |

---

## 3. Component Updates & Layout Refactoring

### Button Component (`app/web/src/components/ui/Button.tsx`)
- Update `borderRadius` to `var(--radius-md)` (8px) instead of pill/10px.
- Primary variant will use solid `var(--ac)` (Coinbase Blue) without shadow.
- Secondary variant will use `background: var(--ac-bg-muted)` (#fafafa) and `border: 1px solid var(--ac-border)`.

### Sidebar Navigation (`app/web/src/components/shell/Sidebar.tsx`)
- Apply `borderRadius: var(--radius-sm)` (6px) to all links.
- Sidebar background set to `#ffffff` and `borderRight: 1px solid var(--ac-border)`.
- Replace all emoji icons with Lucide icons.
- Update profile details and Modal popup rows with clean Lucide icons.

### Chat Page (`app/web/src/routes/chat/ChatPage.tsx`)
- **Header:** Model selector uses standard select box with `border: 1px solid var(--ac-border)` and `borderRadius: var(--radius-md)`.
- **Suggestions:** Grid cards use `borderRadius: var(--radius-lg)` (12px), `border: 1px solid var(--ac-border)`, and Lucide category icons.
- **User Messages:** Bubbles use `background: var(--ac)`, text `#ffffff`, and `borderRadius: "12px 12px 0 12px"`.
- **Agent Messages:** Cards use `#ffffff` background, `border: 1px solid var(--ac-border)`, and `borderRadius: var(--radius-lg)`.
- **Input Composer:** Form wrapper uses `borderRadius: var(--radius-md)` (8px) and border `1px solid var(--ac-border)`. The Ask button is fully square-rounded `8px` with Lucide `ArrowUp`.

### Agent Visualizations (`app/web/src/routes/chat/AgentVisualization.tsx`)
- Font updated to `JetBrains Mono` for tabular data.
- **Diagnostic:** Citations styled in `#fafafa` cards with left border `2px solid var(--ac)`.
- **Predictive:** SVGs have container with `borderRadius: var(--radius-lg)` and thin borders. Chart line stroke set to `var(--ac)`.
- **Prescriptive:** Table header uses `#fafafa` and clean headers without emojis.

---

## 4. Verification & Scope
We will test the compilation of the `web` workspace and verify the UI looks consistent and compiles without TypeScript warnings.
