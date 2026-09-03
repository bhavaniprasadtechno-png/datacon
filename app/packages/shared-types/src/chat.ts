export type ChatIntent = "descriptive" | "diagnostic" | "predictive" | "prescriptive" | "general";

export type Confidence = "high" | "medium" | "low";

export interface AgentTable {
  columns: string[];
  rows: (string | number | boolean | null)[][];
}

export interface ChartPoint {
  label: string;
  value: number;
  lower?: number;
  upper?: number;
}

export interface AgentChart {
  type: "bar" | "line" | "horizontal_bar";
  title: string;
  data: ChartPoint[];
}

export interface Citation {
  id: number;
  documentTitle: string;
  filename: string;
  chunkIndex: number;
  snippet: string;
}

export interface PrescriptiveAction {
  title: string;
  // Unset for actions built by the migrated Prescriptive pipeline (see
  // StructuredResponse.actions below) — it was never rendered, only carried
  // by the pre-migration flat payload shape.
  impact?: string;
  effort: "Low" | "Medium" | "High";
  owner: string;
  rationale: string;
  expectedImpact: string;
  citationIds?: number[];
}

export interface AgentPayload {
  confidence: Confidence;
  table?: AgentTable;
  chart?: AgentChart;
  citations?: Citation[];
  actions?: PrescriptiveAction[];
  correlation?: string;
}

// --- Structured response contract -------------------------------------
// Mirrors app/ai/app/pipeline/contracts.py's StructuredResponse. Emitted by
// analysts migrated onto the new pipeline (currently: descriptive) as the
// full payload shape; analysts not yet migrated still emit AgentPayload
// above. The adapter in `lib/payloadAdapter.ts` normalizes both into one
// shape the renderer consumes.

export type MetricFormat = "number" | "percentage" | "currency" | "text";
export type InsightType = "positive" | "attention" | "neutral";

export type VisualizationType =
  | "kpi" | "line" | "area" | "bar" | "horizontal_bar" | "stacked_bar" | "grouped_bar"
  | "donut" | "pie" | "funnel" | "scatter" | "histogram" | "heatmap" | "table"
  | "ranking" | "timeline" | "map" | "none";

export interface Summary {
  text: string;
  confidence: Confidence;
}

export interface Metric {
  id: string;
  label: string;
  value: number | string;
  format: MetricFormat;
}

export interface Insight {
  type: InsightType;
  text: string;
  evidence: string[];
}

export interface Visualization {
  type: VisualizationType;
  title: string | null;
  data: Record<string, unknown>[];
  dimension?: string | null;
  measure?: string | null;
}

export interface StructuredTable {
  columns: string[];
  rows: (string | number | boolean | null)[][];
  collapsed: boolean;
}

export interface Source {
  dataset: string;
  rowCount: number;
}

export interface StructuredResponse {
  summary: Summary;
  metrics: Metric[];
  insights: Insight[];
  visualizations: Visualization[];
  tables: StructuredTable[];
  sources: Source[];
  // Reuses PrescriptiveAction's shape (minus `impact`, which the migrated
  // pipeline's Action contract never populates) rather than introducing a
  // second, structurally-identical TS type.
  actions: PrescriptiveAction[];
}

export const CHAT_SUGGESTIONS: { intent: Exclude<ChatIntent, "general">; question: string }[] = [
  { intent: "descriptive", question: "Summarize revenue by region last quarter" },
  { intent: "diagnostic", question: "Why did EMEA support tickets spike this week?" },
  { intent: "predictive", question: "Forecast revenue for the next two quarters" },
  { intent: "prescriptive", question: "What should we do to reduce churn this quarter?" },
];

export const INTENT_META: Record<string, { label: string; color: string; bg: string }> = {
  descriptive: { label: "Descriptive agent", color: "var(--ac)", bg: "var(--ac-soft)" },
  diagnostic: { label: "Diagnostic agent", color: "var(--intent-diagnostic-color)", bg: "var(--intent-diagnostic-bg)" },
  predictive: { label: "Predictive agent", color: "var(--intent-predictive-color)", bg: "var(--intent-predictive-bg)" },
  prescriptive: { label: "Prescriptive agent", color: "var(--intent-prescriptive-color)", bg: "var(--intent-prescriptive-bg)" },
  general: { label: "General agent", color: "var(--intent-general-color)", bg: "var(--intent-general-bg)" },
};

// Keep in sync with app/ai/app/llm/models.py's AVAILABLE_MODELS — this is
// the picker shown in chat; that file is what the ai service accepts/
// validates a per-request model override against.
export interface LlmModelOption {
  id: string;
  label: string;
  description: string;
}

export const AVAILABLE_LLM_MODELS: LlmModelOption[] = [
  { id: "Qwen/Qwen3.7-Plus", label: "Qwen 3.7 Plus", description: "Together AI high performance model" },
];
