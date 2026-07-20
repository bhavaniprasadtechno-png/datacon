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
