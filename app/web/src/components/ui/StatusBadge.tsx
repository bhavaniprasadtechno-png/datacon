import type { AccountStatus } from "../../api/platformAdmin";

export function StatusBadge({ status }: { status: AccountStatus }) {
  const active = status === "ACTIVE";
  return (
    <span
      style={{
        font: "600 10px 'IBM Plex Mono',monospace",
        padding: "3px 9px",
        borderRadius: 20,
        color: active ? "#0f8a5c" : "#c0405a",
        background: active ? "#e6f6ee" : "#fbe8ea",
        whiteSpace: "nowrap",
      }}
    >
      {active ? "ACTIVE" : "SUSPENDED"}
    </span>
  );
}
