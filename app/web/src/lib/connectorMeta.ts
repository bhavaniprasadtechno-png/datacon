import type { ConnectorEngineId } from "@datacon/shared-types";
import type { ConnectorStatus } from "./types";

export const TYPE_STYLE: Record<ConnectorEngineId, { letter: string; bg: string; color: string }> = {
  postgres: { letter: "P", bg: "var(--connector-badge-bg, #e9eefc)", color: "#3b6fd4" },
  supabase: { letter: "U", bg: "var(--connector-badge-bg, #e6f9f0)", color: "#1a9c6b" },
  mysql: { letter: "M", bg: "var(--connector-badge-bg, #fdf0e6)", color: "#d9822b" },
  snowflake: { letter: "S", bg: "var(--connector-badge-bg, #e3f6fb)", color: "#2ba6c4" },
  bigquery: { letter: "B", bg: "var(--connector-badge-bg, #eef0f4)", color: "#5a6b86" },
  sqlite: { letter: "L", bg: "var(--connector-badge-bg, #e6f6ee)", color: "#3a9d6a" },
  mongodb: { letter: "G", bg: "var(--connector-badge-bg, #e6f6ee)", color: "#1d8e5a" },
  http: { letter: "H", bg: "var(--ac-soft)", color: "var(--ac)" },
  s3: { letter: "S3", bg: "var(--connector-badge-bg, #fdf3e3)", color: "#b9791f" },
  azure: { letter: "A", bg: "var(--connector-badge-bg, #e9f2fd)", color: "#2a6fc9" },
  gcs: { letter: "G", bg: "var(--connector-badge-bg, #eef0f4)", color: "#5a6b86" },
};

export const STATUS_META: Record<ConnectorStatus, { label: string; color: string; bg: string; dot: string }> = {
  SYNCED: { label: "Synced", color: "var(--sem-success-color, #0f8a5c)", bg: "var(--sem-success-bg, #e6f7ef)", dot: "#1bbf6b" },
  SYNCING: { label: "Syncing", color: "var(--sem-warning-color, #b9743a)", bg: "var(--sem-warning-bg, #fbeede)", dot: "#d9a23a" },
  ERROR: { label: "Sync failed", color: "var(--sem-error-color, #c0392b)", bg: "var(--sem-error-bg, #fdeee9)", dot: "#e2603f" },
  PENDING: { label: "Pending", color: "#71768a", bg: "var(--ac-bg)", dot: "#a3a8bd" },
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
