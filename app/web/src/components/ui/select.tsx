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
>(({ children, style, align = "end", sideOffset = 4, position = "popper", ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      position={position}
      className="select-content"
      style={{
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
