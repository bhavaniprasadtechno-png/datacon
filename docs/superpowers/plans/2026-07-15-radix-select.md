# Radix Select Dropdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the original shadcn-style select dropdown using `@radix-ui/react-select` primitive, styled with vanilla CSS/inline properties to match the Coinbase / slate design system.

**Architecture:** We will add CSS rules for `.select-item[data-highlighted]` and animations in `tokens.css`, create the React sub-components (`Select`, `SelectTrigger`, `SelectValue`, `SelectContent`, `SelectItem`) in a new `select.tsx` UI file, and replace the native select picker in `ChatPage.tsx` with it.

**Tech Stack:** React, Radix UI Select Primitive, Lucide React, CSS.

---

### Task 1: CSS Animation & Highlight Styles

**Files:**
- Modify: `app/web/src/styles/tokens.css`

- [ ] **Step 1: Add Radix select item highlight and animation CSS**
  Open [tokens.css](file:///c:/Users/pc/Desktop/datacon/app/web/src/styles/tokens.css) and append the following styles at the bottom:
  ```css
  /* Radix UI Select component styles (shadcn spec) */
  .select-content {
    animation: select-fade-in 0.1s cubic-bezier(0.16, 1, 0.3, 1);
  }
  @keyframes select-fade-in {
    from { opacity: 0; transform: translateY(2px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .select-item {
    position: relative;
    display: flex;
    align-items: center;
    padding: 6px 8px 6px 28px;
    font-size: 11.5px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--ac-fg);
    border-radius: var(--radius-sm);
    cursor: pointer;
    outline: none;
    user-select: none;
  }
  .select-item[data-highlighted] {
    background: var(--ac-bg-muted);
    color: var(--ac-fg);
  }
  ```

---

### Task 2: Implementing the Select Component

**Files:**
- Create: `app/web/src/components/ui/select.tsx`

- [ ] **Step 1: Create the custom Select components**
  Create [select.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/components/ui/select.tsx) and implement it using Radix UI primitives:
  ```tsx
  import * as React from "react";
  import * as SelectPrimitive from "@radix-ui/react-select";
  import { Check, ChevronDown } from "lucide-react";

  export const Select = SelectPrimitive.Root;
  export const SelectValue = SelectPrimitive.Value;

  export const SelectTrigger = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.Trigger>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
  >(({ children, style, ...props }, ref) => (
    <SelectPrimitive.Trigger
      ref={ref}
      style={{
        display: "flex",
        height: 32,
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--ac-border)",
        padding: "0 12px",
        fontSize: "11.5px",
        background: "#fff",
        cursor: "pointer",
        outline: "none",
        color: "var(--ac-fg)",
        fontFamily: "'JetBrains Mono',monospace",
        fontWeight: 600,
        minWidth: 155,
        ...style,
      }}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown size={14} style={{ color: "var(--ac-muted)" }} />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  ));
  SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

  export const SelectContent = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.Content>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
  >(({ children, style, ...props }, ref) => (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        ref={ref}
        className="select-content"
        style={{
          position: "relative",
          zIndex: 50,
          background: "#fff",
          border: "1px solid var(--ac-border)",
          borderRadius: "var(--radius-md)",
          boxShadow: "0 10px 15px -3px rgba(0,0,0,0.06), 0 4px 6px -4px rgba(0,0,0,0.06)",
          minWidth: 160,
          padding: 4,
          ...style,
        }}
        {...props}
      >
        <SelectPrimitive.Viewport style={{ padding: 2 }}>
          {children}
        </SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  ));
  SelectContent.displayName = SelectPrimitive.Content.displayName;

  export const SelectItem = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.Item>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
  >(({ children, style, ...props }, ref) => (
    <SelectPrimitive.Item
      ref={ref}
      className="select-item"
      style={{
        ...style,
      }}
      {...props}
    >
      <span style={{ position: "absolute", left: 8, display: "inline-flex", width: 14, height: 14, alignItems: "center", justifyContent: "center" }}>
        <SelectPrimitive.ItemIndicator>
          <Check size={12} />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  ));
  SelectItem.displayName = SelectPrimitive.Item.displayName;
  ```

---

### Task 3: Replace Model Picker in ChatPage

**Files:**
- Modify: `app/web/src/routes/chat/ChatPage.tsx`

- [ ] **Step 1: Import custom Select component**
  Open [ChatPage.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/routes/chat/ChatPage.tsx). Import the Select sub-components:
  ```typescript
  import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
  ```

- [ ] **Step 2: Replace native HTML select element with Custom Select**
  Replace the `<select>` element (around line 144) with:
  ```tsx
  <Select value={model} onValueChange={setModel}>
    <SelectTrigger title="LLM model for this chat">
      <SelectValue placeholder="Select model" />
    </SelectTrigger>
    <SelectContent>
      {AVAILABLE_LLM_MODELS.map((m) => (
        <SelectItem key={m.id} value={m.id}>
          {m.label}
        </SelectItem>
      ))}
    </SelectContent>
  </Select>
  ```

- [ ] **Step 3: Compile and verify workspace type safety**
  Run: `npx tsc --noEmit` in `app/web`
  Expected: SUCCESS (no type errors)

- [ ] **Step 4: Run a full production build**
  Run: `npm run build` in `app`
  Expected: SUCCESS
