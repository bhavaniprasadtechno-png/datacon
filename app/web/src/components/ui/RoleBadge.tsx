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
