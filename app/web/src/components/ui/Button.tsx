import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

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

export function Button({ variant = "secondary", style, disabled, ...rest }: Props) {
  return (
    <button
      {...rest}
      disabled={disabled}
      style={{
        ...base,
        ...variants[variant],
        opacity: disabled ? 0.55 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        ...style,
      }}
      onMouseEnter={(e) => {
        if (!disabled) e.currentTarget.style.filter = "brightness(1.05)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.filter = "none";
      }}
    />
  );
}
