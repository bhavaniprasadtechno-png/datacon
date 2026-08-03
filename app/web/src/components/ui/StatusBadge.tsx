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
