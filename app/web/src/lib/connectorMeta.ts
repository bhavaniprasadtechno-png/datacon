import type { ConnectorEngineId } from "@datacon/shared-types";
import type { ConnectorStatus } from "./types";

export const TYPE_STYLE: Record<ConnectorEngineId, { letter: string; bg: string; color: string }> = {
  postgres: { letter: "P", bg: "#e9eefc", color: "#3b6fd4" },
  supabase: { letter: "U", bg: "#e6f9f0", color: "#1a9c6b" },
  mysql: { letter: "M", bg: "#fdf0e6", color: "#d9822b" },
  snowflake: { letter: "S", bg: "#e3f6fb", color: "#2ba6c4" },
  bigquery: { letter: "B", bg: "#eef0f4", color: "#5a6b86" },
  sqlite: { letter: "L", bg: "#e6f6ee", color: "#3a9d6a" },
  mongodb: { letter: "G", bg: "#e6f6ee", color: "#1d8e5a" },
  http: { letter: "H", bg: "var(--ac-soft)", color: "var(--ac)" },
};

export const STATUS_META: Record<ConnectorStatus, { label: string; color: string; bg: string; dot: string }> = {
  SYNCED: { label: "Synced", color: "#0f8a5c", bg: "#e6f7ef", dot: "#1bbf6b" },
  SYNCING: { label: "Syncing", color: "#b9743a", bg: "#fbeede", dot: "#d9a23a" },
  ERROR: { label: "Sync failed", color: "#c0392b", bg: "#fdeee9", dot: "#e2603f" },
  PENDING: { label: "Pending", color: "#71768a", bg: "#f0f1f6", dot: "#a3a8bd" },
};

export function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.round(ms / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} hr ago`;
  return `${Math.round(hr / 24)}d ago`;
}
