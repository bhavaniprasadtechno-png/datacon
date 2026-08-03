# Shadcn UI Component Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the custom inline-styled components (`Button`, `Modal`, `AlertDialog`, `Select`, and `Badges`) in `app/web/src/components/ui/` to standard Shadcn UI components styled via Tailwind CSS, while preserving the existing APIs and dynamic runtime theme changes.

**Architecture:** Use the Adapter Pattern to wrap the new Tailwind-styled Shadcn components under the hood, mapping custom props to Shadcn props. Map standard Tailwind CSS variables (like `--color-primary`, `--color-border`, etc.) directly to active theme variables (like `var(--ac)`, `var(--ac-border)`) in `index.css`.

**Tech Stack:** React 19, Tailwind CSS v4, Radix UI primitives, Shadcn CLI.

---

## File Map
The following files will be created or modified:
*   `app/web/src/index.css` (Modify): Re-map Tailwind semantic variables to active theme variables.
*   `app/web/src/components/ui/Button.tsx` (Modify): Rewrite to wrap and map props to `@/components/shadcn-ui/ui/button`.
*   `app/web/src/components/ui/AlertDialog.tsx` (Modify): Replace with standard Shadcn `AlertDialog` exports.
*   `app/web/src/components/ui/select.tsx` (Modify): Replace with standard Shadcn `Select` exports.
*   `app/web/src/components/ui/Modal.tsx` (Modify): Rewrite to wrap and map props to `@/components/shadcn-ui/ui/dialog`.
*   `app/web/src/components/ui/RoleBadge.tsx` (Modify): Rewrite to wrap `@/components/shadcn-ui/ui/badge`.
*   `app/web/src/components/ui/StatusBadge.tsx` (Modify): Rewrite to wrap `@/components/shadcn-ui/ui/badge`.

---

### Task 1: Map Tailwind Variables to Dynamic Theme Tokens
Modify `app/web/src/index.css` to link Tailwind v4 variables (primary, border, input, ring, secondary, accent) to the dynamic CSS variables (`--ac`, `--ac-border`, etc.).

- [ ] **Step 1: Update index.css variable definitions**
  Update the `:root` and `.dark` blocks in `app/web/src/index.css` to route variables dynamically.
  
  File: `app/web/src/index.css`
  Modify lines 52-119:
  ```css
  :root {
      /* Map Shadcn colors to dynamic theme variables */
      --primary: var(--ac);
      --primary-foreground: oklch(1 0 0);
      --border: var(--ac-border);
      --input: var(--ac-border);
      --ring: var(--ac-ring);
      --secondary: var(--ac-bg-muted);
      --secondary-foreground: var(--ac-fg);
      --accent: var(--ac-soft);
      --accent-foreground: var(--ac-fg);

      --background: oklch(1 0 0);
      --foreground: oklch(0.145 0 0);
      --card: oklch(1 0 0);
      --card-foreground: oklch(0.145 0 0);
      --popover: oklch(1 0 0);
      --popover-foreground: oklch(0.145 0 0);
      --destructive: oklch(0.577 0.245 27.325);
      --chart-1: oklch(0.87 0 0);
      --chart-2: oklch(0.556 0 0);
      --chart-3: oklch(0.439 0 0);
      --chart-4: oklch(0.371 0 0);
      --chart-5: oklch(0.269 0 0);
      --radius: 0.625rem;
      --sidebar: oklch(0.985 0 0);
      --sidebar-foreground: oklch(0.145 0 0);
      --sidebar-primary: oklch(0.205 0 0);
      --sidebar-primary-foreground: oklch(0.985 0 0);
      --sidebar-accent: oklch(0.97 0 0);
      --sidebar-accent-foreground: oklch(0.205 0 0);
      --sidebar-border: oklch(0.922 0 0);
      --sidebar-ring: oklch(0.708 0 0);
  }

  .dark {
      --primary: var(--ac);
      --primary-foreground: oklch(0.205 0 0);
      --border: oklch(1 0 0 / 15%);
      --input: oklch(1 0 0 / 20%);
      --ring: var(--ac-ring);
      --secondary: var(--ac-bg-muted);
      --secondary-foreground: var(--ac-fg);
      --accent: var(--ac-soft);
      --accent-foreground: var(--ac-fg);

      --background: oklch(0.145 0 0);
      --foreground: oklch(0.985 0 0);
      --card: oklch(0.205 0 0);
      --card-foreground: oklch(0.985 0 0);
      --popover: oklch(0.205 0 0);
      --popover-foreground: oklch(0.985 0 0);
      --destructive: oklch(0.704 0.191 22.216);
      --chart-1: oklch(0.87 0 0);
      --chart-2: oklch(0.556 0 0);
      --chart-3: oklch(0.439 0 0);
      --chart-4: oklch(0.371 0 0);
      --chart-5: oklch(0.269 0 0);
      --sidebar: oklch(0.205 0 0);
      --sidebar-foreground: oklch(0.985 0 0);
      --sidebar-primary: oklch(0.488 0.243 264.376);
      --sidebar-primary-foreground: oklch(0.985 0 0);
      --sidebar-accent: oklch(0.269 0 0);
      --sidebar-accent-foreground: oklch(0.985 0 0);
      --sidebar-border: oklch(1 0 0 / 10%);
      --sidebar-ring: oklch(0.556 0 0);
  }
  ```

- [ ] **Step 2: Verify styles compile successfully**
  Run: `npm run build` in `app/web`
  Expected: Successful compilation without errors.

---

### Task 2: Install Required Shadcn Components
Install the missing Shadcn components (`dialog`, `select`, `alert-dialog`) using the Shadcn CLI.

- [ ] **Step 1: Run shadcn-ui add commands**
  Run in terminal directory `app/web`:
  `npx shadcn@latest add dialog select alert-dialog --yes --overwrite`
  Expected: The components should be installed in `app/web/src/components/shadcn-ui/ui/`.
  
- [ ] **Step 2: Verify files exist**
  Verify that the following files are created:
  *   `app/web/src/components/shadcn-ui/ui/dialog.tsx`
  *   `app/web/src/components/shadcn-ui/ui/select.tsx`
  *   `app/web/src/components/shadcn-ui/ui/alert-dialog.tsx`

---

### Task 3: Migrate Button Component
Modify `app/web/src/components/ui/Button.tsx` to act as an adapter wrapping Shadcn's button.

- [ ] **Step 1: Replace Button.tsx content**
  File: `app/web/src/components/ui/Button.tsx`
  Replace entire file with:
  ```tsx
  import type { ButtonHTMLAttributes } from "react";
  import { Button as ShadcnButton } from "../shadcn-ui/ui/button";

  type Variant = "primary" | "secondary" | "danger" | "ghost";

  interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: Variant;
  }

  export function Button({ variant = "secondary", className = "", style, ...props }: Props) {
    const variantMap: Record<Variant, "default" | "outline" | "destructive" | "ghost"> = {
      primary: "default",
      secondary: "outline",
      danger: "destructive",
      ghost: "ghost",
    };

    return (
      <ShadcnButton
        variant={variantMap[variant]}
        className={`font-sans font-medium text-[13.5px] rounded-md transition-all duration-150 ${className}`}
        style={style}
        {...props}
      />
    );
  }
  ```

- [ ] **Step 2: Verify project builds successfully**
  Run: `npm run build` in `app/web`
  Expected: Successful compilation.

---

### Task 4: Migrate AlertDialog Component
Overwrite `app/web/src/components/ui/AlertDialog.tsx` with standard Shadcn `AlertDialog` components.

- [ ] **Step 1: Replace AlertDialog.tsx content**
  File: `app/web/src/components/ui/AlertDialog.tsx`
  Replace the custom inline-styled code with standard Shadcn exports.
  
  ```tsx
  import * as React from "react";
  import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
  
  import { cn } from "@/lib/utils";
  import { buttonVariants } from "@/components/shadcn-ui/ui/button";
  
  const AlertDialog = AlertDialogPrimitive.Root;
  const AlertDialogTrigger = AlertDialogPrimitive.Trigger;
  const AlertDialogPortal = AlertDialogPrimitive.Portal;
  
  const AlertDialogOverlay = React.forwardRef<
    React.ElementRef<typeof AlertDialogPrimitive.Overlay>,
    React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Overlay>
  >(({ className, ...props }, ref) => (
    <AlertDialogPrimitive.Overlay
      className={cn(
        "fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
        className
      )}
      {...props}
      ref={ref}
    />
  ));
  AlertDialogOverlay.displayName = AlertDialogPrimitive.Overlay.displayName;
  
  const AlertDialogContent = React.forwardRef<
    React.ElementRef<typeof AlertDialogPrimitive.Content>,
    React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Content>
  >(({ className, ...props }, ref) => (
    <AlertDialogPortal>
      <AlertDialogOverlay />
      <AlertDialogPrimitive.Content
        ref={ref}
        className={cn(
          "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border border-border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-1/2 data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-1/2 rounded-xl",
          className
        )}
        {...props}
      />
    </AlertDialogPortal>
  ));
  AlertDialogContent.displayName = AlertDialogPrimitive.Content.displayName;
  
  const AlertDialogHeader = ({
    className,
    ...props
  }: React.HTMLAttributes<HTMLDivElement>) => (
    <div
      className={cn(
        "flex flex-col space-y-2 text-center sm:text-left",
        className
      )}
      {...props}
    />
  );
  AlertDialogHeader.displayName = "AlertDialogHeader";
  
  const AlertDialogFooter = ({
    className,
    ...props
  }: React.HTMLAttributes<HTMLDivElement>) => (
    <div
      className={cn(
        "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 gap-2",
        className
      )}
      {...props}
    />
  );
  AlertDialogFooter.displayName = "AlertDialogFooter";
  
  const AlertDialogTitle = React.forwardRef<
    React.ElementRef<typeof AlertDialogPrimitive.Title>,
    React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Title>
  >(({ className, ...props }, ref) => (
    <AlertDialogPrimitive.Title
      ref={ref}
      className={cn("text-base font-extrabold text-foreground", className)}
      {...props}
    />
  ));
  AlertDialogTitle.displayName = AlertDialogPrimitive.Title.displayName;
  
  const AlertDialogDescription = React.forwardRef<
    React.ElementRef<typeof AlertDialogPrimitive.Description>,
    React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Description>
  >(({ className, ...props }, ref) => (
    <AlertDialogPrimitive.Description
      ref={ref}
      className={cn("text-[13px] text-muted-foreground leading-normal", className)}
      {...props}
    />
  ));
  AlertDialogDescription.displayName =
    AlertDialogPrimitive.Description.displayName;
  
  const AlertDialogAction = React.forwardRef<
    React.ElementRef<typeof AlertDialogPrimitive.Action>,
    React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Action> & { variant?: "primary" | "danger" }
  >(({ className, variant = "primary", ...props }, ref) => (
    <AlertDialogPrimitive.Action
      ref={ref}
      className={cn(
        buttonVariants({ variant: variant === "danger" ? "destructive" : "default" }),
        className
      )}
      {...props}
    />
  ));
  AlertDialogAction.displayName = AlertDialogPrimitive.Action.displayName;
  
  const AlertDialogCancel = React.forwardRef<
    React.ElementRef<typeof AlertDialogPrimitive.Cancel>,
    React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Cancel>
  >(({ className, ...props }, ref) => (
    <AlertDialogPrimitive.Cancel
      ref={ref}
      className={cn(
        buttonVariants({ variant: "outline" }),
        "mt-2 sm:mt-0",
        className
      )}
      {...props}
    />
  ));
  AlertDialogCancel.displayName = AlertDialogPrimitive.Cancel.displayName;
  
  export {
    AlertDialog,
    AlertDialogPortal,
    AlertDialogOverlay,
    AlertDialogTrigger,
    AlertDialogContent,
    AlertDialogHeader,
    AlertDialogFooter,
    AlertDialogTitle,
    AlertDialogDescription,
    AlertDialogAction,
    AlertDialogCancel,
  };
  ```

- [ ] **Step 2: Verify project builds successfully**
  Run: `npm run build` in `app/web`
  Expected: Successful compilation.

---

### Task 5: Migrate Select Component
Overwrite `app/web/src/components/ui/select.tsx` with standard Shadcn `Select` components.

- [ ] **Step 1: Replace select.tsx content**
  File: `app/web/src/components/ui/select.tsx`
  Replace the custom inline-styled select file with standard Shadcn select.
  
  ```tsx
  import * as React from "react";
  import * as SelectPrimitive from "@radix-ui/react-select";
  import { Check, ChevronDown, ChevronUp } from "lucide-react";
  
  import { cn } from "@/lib/utils";
  
  const Select = SelectPrimitive.Root;
  const SelectGroup = SelectPrimitive.Group;
  const SelectValue = SelectPrimitive.Value;
  
  const SelectTrigger = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.Trigger>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
  >(({ className, children, ...props }, ref) => (
    <SelectPrimitive.Trigger
      ref={ref}
      className={cn(
        "flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-xs font-semibold font-mono tracking-wide ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1 min-w-[155px] cursor-pointer",
        className
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown className="h-4 w-4 opacity-50" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  ));
  SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;
  
  const SelectScrollUpButton = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.ScrollUpButton>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollUpButton>
  >(({ className, ...props }, ref) => (
    <SelectPrimitive.ScrollUpButton
      ref={ref}
      className={cn(
        "flex cursor-default items-center justify-center py-1",
        className
      )}
      {...props}
    >
      <ChevronUp className="h-4 w-4" />
    </SelectPrimitive.ScrollUpButton>
  ));
  SelectScrollUpButton.displayName =
    SelectPrimitive.ScrollUpButton.displayName;
  
  const SelectScrollDownButton = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.ScrollDownButton>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollDownButton>
  >(({ className, ...props }, ref) => (
    <SelectPrimitive.ScrollDownButton
      ref={ref}
      className={cn(
        "flex cursor-default items-center justify-center py-1",
        className
      )}
      {...props}
    >
      <ChevronDown className="h-4 w-4" />
    </SelectPrimitive.ScrollDownButton>
  ));
  SelectScrollDownButton.displayName =
    SelectPrimitive.ScrollDownButton.displayName;
  
  const SelectContent = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.Content>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
  >(({ className, children, position = "popper", ...props }, ref) => (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        ref={ref}
        className={cn(
          "relative z-50 max-h-96 min-w-[8rem] overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",
          position === "popper" &&
            "data-[side=bottom]:translate-y-1 data-[side=left]:-translate-x-1 data-[side=right]:translate-x-1 data-[side=top]:-translate-y-1",
          className
        )}
        position={position}
        {...props}
      >
        <SelectScrollUpButton />
        <SelectPrimitive.Viewport
          className={cn(
            "p-1",
            position === "popper" &&
              "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]"
          )}
        >
          {children}
        </SelectPrimitive.Viewport>
        <SelectScrollDownButton />
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  ));
  SelectContent.displayName = SelectPrimitive.Content.displayName;
  
  const SelectLabel = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.Label>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.Label>
  >(({ className, ...props }, ref) => (
    <SelectPrimitive.Label
      ref={ref}
      className={cn("py-1.5 pl-8 pr-2 text-xs font-semibold", className)}
      {...props}
    />
  ));
  SelectLabel.displayName = SelectPrimitive.Label.displayName;
  
  const SelectItem = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.Item>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
  >(({ className, children, ...props }, ref) => (
    <SelectPrimitive.Item
      ref={ref}
      className={cn(
        "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-xs font-mono font-medium outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50 cursor-pointer",
        className
      )}
      {...props}
    >
      <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <Check className="h-3 w-3" />
        </SelectPrimitive.ItemIndicator>
      </span>
  
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  ));
  SelectItem.displayName = SelectPrimitive.Item.displayName;
  
  const SelectSeparator = React.forwardRef<
    React.ElementRef<typeof SelectPrimitive.Separator>,
    React.ComponentPropsWithoutRef<typeof SelectPrimitive.Separator>
  >(({ className, ...props }, ref) => (
    <SelectPrimitive.Separator
      ref={ref}
      className={cn("-mx-1 my-1 h-px bg-muted", className)}
      {...props}
    />
  ));
  SelectSeparator.displayName = SelectPrimitive.Separator.displayName;
  
  export {
    Select,
    SelectGroup,
    SelectValue,
    SelectTrigger,
    SelectContent,
    SelectLabel,
    SelectItem,
    SelectSeparator,
    SelectScrollUpButton,
    SelectScrollDownButton,
  };
  ```

- [ ] **Step 2: Verify project builds successfully**
  Run: `npm run build` in `app/web`
  Expected: Successful compilation.

---

### Task 6: Migrate Modal Component
Rewrite `app/web/src/components/ui/Modal.tsx` to adapt and wrap Shadcn's `Dialog`.

- [ ] **Step 1: Replace Modal.tsx content**
  File: `app/web/src/components/ui/Modal.tsx`
  Replace custom modal implementation with adapter wrapping Shadcn Dialog.
  
  ```tsx
  import type { ReactNode } from "react";
  import { Dialog, DialogContent, DialogTitle, DialogDescription } from "../shadcn-ui/ui/dialog";
  import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
  import { cn } from "@/lib/utils";
  
  interface Props {
    open: boolean;
    onClose: () => void;
    width?: number;
    children: ReactNode;
    z?: number;
  }
  
  export function Modal({ open, onClose, children, width = 440 }: Props) {
    return (
      <Dialog open={open} onOpenChange={(val) => { if (!val) onClose(); }}>
        <DialogContent 
          className="max-h-[90vh] overflow-y-auto rounded-xl p-5 shadow-lg border-border bg-background"
          style={{ maxWidth: `min(${width}px, 92vw)` }}
        >
          {/* Ensure screen readers have access to title and description */}
          <VisuallyHidden>
            <DialogTitle>Dialog</DialogTitle>
            <DialogDescription>Content details</DialogDescription>
          </VisuallyHidden>
          {children}
        </DialogContent>
      </Dialog>
    );
  }
  
  export function ModalHeader({ title, onClose }: { title: string; onClose: () => void }) {
    return (
      <div className="flex items-center justify-between mb-4">
        <div className="text-[17px] font-extrabold text-foreground">{title}</div>
        <button onClick={onClose} className="text-[16px] text-muted-foreground hover:text-foreground">
          ✕
        </button>
      </div>
    );
  }
  ```

- [ ] **Step 2: Verify project builds successfully**
  Run: `npm run build` in `app/web`
  Expected: Successful compilation.

---

### Task 7: Migrate Badges
Rewrite `RoleBadge.tsx` and `StatusBadge.tsx` to wrap and styled with Shadcn's `Badge`.

- [ ] **Step 1: Replace RoleBadge.tsx content**
  File: `app/web/src/components/ui/RoleBadge.tsx`
  Replace custom role badge with a styled Shadcn badge wrapper.
  
  ```tsx
  import { Badge } from "../shadcn-ui/ui/badge";
  
  export function RoleBadge({ name, color, bg }: { name: string; color?: string | null; bg?: string | null }) {
    return (
      <Badge
        variant="outline"
        style={{
          color: color ?? "#71768a",
          backgroundColor: bg ?? "#f0f1f6",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "10px",
          fontWeight: 600,
          textTransform: "uppercase",
        }}
        className="px-2.5 py-1 whitespace-nowrap rounded-full border-none"
      >
        {name}
      </Badge>
    );
  }
  ```

- [ ] **Step 2: Replace StatusBadge.tsx content**
  File: `app/web/src/components/ui/StatusBadge.tsx`
  Replace custom status badge with a Tailwind-styled Shadcn badge.
  
  ```tsx
  import { Badge } from "../shadcn-ui/ui/badge";
  import type { AccountStatus } from "../../api/platformAdmin";
  
  export function StatusBadge({ status }: { status: AccountStatus }) {
    const active = status === "ACTIVE";
    return (
      <Badge
        variant={active ? "default" : "destructive"}
        className="px-2.5 py-1 font-mono text-[10px] font-semibold tracking-wide whitespace-nowrap bg-emerald-500/10 text-emerald-600 border-emerald-500/20 data-[variant=destructive]:bg-red-500/10 data-[variant=destructive]:text-red-600 data-[variant=destructive]:border-red-500/20 rounded-full border"
        style={{
          fontFamily: "'IBM Plex Mono', monospace",
          textTransform: "uppercase",
        }}
      >
        {active ? "ACTIVE" : "SUSPENDED"}
      </Badge>
    );
  }
  ```

- [ ] **Step 3: Verify project builds successfully**
  Run: `npm run build` in `app/web`
  Expected: Successful compilation.

---

### Task 8: Final Build and Verification
Perform a complete clean compilation check on the `web` workspace.

- [ ] **Step 1: Clean build**
  Run in `app/web`: `npm run build`
  Expected: Successful production build without TypeScript errors.
