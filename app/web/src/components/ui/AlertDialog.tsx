import * as React from "react";
import * as ShadcnAlertDialog from "../shadcn-ui/ui/alert-dialog";

export const AlertDialog = ShadcnAlertDialog.AlertDialog;
export const AlertDialogTrigger = ShadcnAlertDialog.AlertDialogTrigger;
export const AlertDialogPortal = ShadcnAlertDialog.AlertDialogPortal;
export const AlertDialogOverlay = ShadcnAlertDialog.AlertDialogOverlay;
export const AlertDialogContent = ShadcnAlertDialog.AlertDialogContent;
export const AlertDialogHeader = ShadcnAlertDialog.AlertDialogHeader;
export const AlertDialogFooter = ShadcnAlertDialog.AlertDialogFooter;
export const AlertDialogTitle = ShadcnAlertDialog.AlertDialogTitle;
export const AlertDialogDescription = ShadcnAlertDialog.AlertDialogDescription;
export const AlertDialogCancel = ShadcnAlertDialog.AlertDialogCancel;

interface ActionProps extends Omit<React.ComponentPropsWithoutRef<typeof ShadcnAlertDialog.AlertDialogAction>, "variant"> {
  variant?: "primary" | "danger";
}

export function AlertDialogAction({ variant, ...props }: ActionProps) {
  const variantMap = {
    primary: "default" as const,
    danger: "destructive" as const,
  };

  return (
    <ShadcnAlertDialog.AlertDialogAction
      variant={variant ? variantMap[variant] : undefined}
      {...props}
    />
  );
}
