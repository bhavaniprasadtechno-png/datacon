# Custom Alert Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the browser's default `window.confirm` dialog in the sidebar with a reusable, styled Radix UI Alert Dialog component matching the application theme.

**Architecture:** We will create a set of reusable Radix UI `@radix-ui/react-alert-dialog` primitives, use them to update the global `ConfirmHost` component, and call the promise-based `confirm()` hook in `Sidebar` to trigger the confirmation.

**Tech Stack:** React, `@radix-ui/react-alert-dialog`, TypeScript, CSS custom properties.

---

### Task 1: Create Reusable Radix UI Alert Dialog Primitives

**Files:**
- Create: `app/web/src/components/ui/AlertDialog.tsx`

- [ ] **Step 1: Create the custom `AlertDialog.tsx` component wrapper**

Create [AlertDialog.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/components/ui/AlertDialog.tsx) with the following content:

```tsx
import * as React from "react";
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import { Button } from "./Button";

export const AlertDialog = AlertDialogPrimitive.Root;
export const AlertDialogTrigger = AlertDialogPrimitive.Trigger;
export const AlertDialogPortal = AlertDialogPrimitive.Portal;

export const AlertDialogOverlay = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Overlay>
>(({ style, ...props }, ref) => (
  <AlertDialogPrimitive.Overlay
    ref={ref}
    style={{
      position: "fixed",
      inset: 0,
      background: "rgba(26, 29, 41, 0.42)",
      backdropFilter: "blur(3px)",
      zIndex: 60,
      ...style,
    }}
    {...props}
  />
));
AlertDialogOverlay.displayName = AlertDialogPrimitive.Overlay.displayName;

export const AlertDialogContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Content> & { width?: number }
>(({ style, width = 400, ...props }, ref) => (
  <AlertDialogPortal>
    <AlertDialogOverlay />
    <div
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 60,
        pointerEvents: "none",
      }}
    >
      <AlertDialogPrimitive.Content
        ref={ref}
        style={{
          width,
          maxWidth: "92vw",
          maxHeight: "90vh",
          overflowY: "auto",
          background: "#fff",
          borderRadius: 18,
          boxShadow: "0 30px 70px -20px rgba(26, 29, 41, 0.5)",
          padding: 22,
          pointerEvents: "auto",
          ...style,
        }}
        {...props}
      />
    </div>
  </AlertDialogPortal>
));
AlertDialogContent.displayName = AlertDialogPrimitive.Content.displayName;

export const AlertDialogHeader = ({
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: 6,
      marginBottom: 16,
      ...style,
    }}
    {...props}
  />
);
AlertDialogHeader.displayName = "AlertDialogHeader";

export const AlertDialogFooter = ({
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    style={{
      display: "flex",
      justifyContent: "flex-end",
      gap: 10,
      marginTop: 20,
      ...style,
    }}
    {...props}
  />
);
AlertDialogFooter.displayName = "AlertDialogFooter";

export const AlertDialogTitle = React.forwardRef<
  HTMLHeadingElement,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Title>
>(({ style, ...props }, ref) => (
  <AlertDialogPrimitive.Title
    ref={ref}
    style={{
      fontSize: 16,
      fontWeight: 800,
      margin: 0,
      color: "var(--ac-fg)",
      ...style,
    }}
    {...props}
  />
));
AlertDialogTitle.displayName = AlertDialogPrimitive.Title.displayName;

export const AlertDialogDescription = React.forwardRef<
  HTMLParagraphElement,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Description>
>(({ style, ...props }, ref) => (
  <AlertDialogPrimitive.Description
    ref={ref}
    style={{
      fontSize: 13,
      color: "#71768a",
      margin: 0,
      lineHeight: 1.5,
      ...style,
    }}
    {...props}
  />
));
AlertDialogDescription.displayName =
  AlertDialogPrimitive.Description.displayName;

export const AlertDialogAction = React.forwardRef<
  HTMLButtonElement,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Action> & { variant?: "primary" | "danger" }
>(({ variant = "primary", ...props }, ref) => (
  <AlertDialogPrimitive.Action ref={ref} asChild>
    <Button variant={variant} {...props} />
  </AlertDialogPrimitive.Action>
));
AlertDialogAction.displayName = AlertDialogPrimitive.Action.displayName;

export const AlertDialogCancel = React.forwardRef<
  HTMLButtonElement,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Cancel>
>((props, ref) => (
  <AlertDialogPrimitive.Cancel ref={ref} asChild>
    <Button variant="secondary" {...props} />
  </AlertDialogPrimitive.Cancel>
));
AlertDialogCancel.displayName = AlertDialogPrimitive.Cancel.displayName;
```

---

### Task 2: Refactor ConfirmHost to use the Radix AlertDialog

**Files:**
- Modify: `app/web/src/components/ui/ConfirmHost.tsx`

- [ ] **Step 1: Replace ConfirmHost content to use new AlertDialog components**

Modify [ConfirmHost.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/components/ui/ConfirmHost.tsx) to replace the manual CSS `Modal` with `AlertDialog`:

```tsx
import { useConfirmStore } from "../../stores/useConfirmStore";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from "./AlertDialog";

export function ConfirmHost() {
  const pending = useConfirmStore((state) => state.pending);
  const resolve = useConfirmStore((state) => state.resolve);

  return (
    <AlertDialog open={!!pending} onOpenChange={(open) => { if (!open) resolve(false); }}>
      {pending && (
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{pending.title}</AlertDialogTitle>
            <AlertDialogDescription>{pending.body}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => resolve(false)}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant={pending.tone === "danger" ? "danger" : "primary"}
              onClick={() => resolve(true)}
            >
              {pending.label}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      )}
    </AlertDialog>
  );
}
```

---

### Task 3: Integrate Custom Confirm in Sidebar

**Files:**
- Modify: `app/web/src/components/shell/Sidebar.tsx`

- [ ] **Step 1: Modify `Sidebar.tsx` to call `useConfirm`**

Update `removeConversation` in [Sidebar.tsx](file:///c:/Users/pc/Desktop/datacon/app/web/src/components/shell/Sidebar.tsx):
- Import `useConfirm` from `../../stores/useConfirmStore`.
- Call `const confirm = useConfirm();` inside the `Sidebar` component definition.
- Replace `window.confirm` with a call to the programmatic hook `confirm({...})`.

Specifically, import:
```tsx
import { useConfirm } from "../../stores/useConfirmStore";
```

Call hook:
```tsx
  const confirm = useConfirm();
```

Replace `removeConversation`:
```tsx
  const removeConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const ok = await confirm({
      title: "Delete conversation",
      body: "Are you sure you want to delete this conversation? This action cannot be undone.",
      label: "Delete",
      tone: "danger"
    });
    if (!ok) return;
    await deleteConversation.mutateAsync(id);
    // If the open conversation was just deleted, fall back to the default
    // (most recent / freshly created) one by dropping the URL param.
    if (id === activeConversationId) navigate("/chat", { replace: true });
  };
```

---

### Task 4: Integrate Custom Confirm in Other Pages

**Files:**
- Modify: `app/web/src/routes/chat/ChatHistoryPage.tsx`
- Modify: `app/web/src/routes/data-sources/DataSourcesPage.tsx`

- [ ] **Step 1: Update `ChatHistoryPage.tsx`**
Import and use `useConfirm` inside `ChatHistoryPage` to confirm deleting a conversation:
```tsx
import { useConfirm } from "../../stores/useConfirmStore";
// ...
const confirm = useConfirm();
// ...
const removeConversation = async (id: string, e: React.MouseEvent) => {
  e.stopPropagation();
  const ok = await confirm({
    title: "Delete conversation",
    body: "Delete this conversation? This can't be undone.",
    label: "Delete",
    tone: "danger",
  });
  if (!ok) return;
  await deleteConversation.mutateAsync(id);
};
```

- [ ] **Step 2: Update `DataSourcesPage.tsx`**
Import and use `useConfirm` inside `DataSourcesPage` to confirm deleting a data source:
```tsx
import { useConfirm } from "../../stores/useConfirmStore";
// ...
const confirm = useConfirm();
// ...
const removeRow = async (row: DataSourceRecord) => {
  const ok = await confirm({
    title: "Delete data source",
    body: `Delete "${row.title}"? This can't be undone.`,
    label: "Delete",
    tone: "danger",
  });
  if (!ok) return;
  deleteDataSource.mutate(row.id);
};
```

---

### Task 5: Compilation and Build Verification

- [ ] **Step 1: Run production build**

Run command in `app/web`:
```bash
npm run build
```
Expected output: Successful build with zero errors.

