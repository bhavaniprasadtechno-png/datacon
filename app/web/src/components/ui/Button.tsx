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
