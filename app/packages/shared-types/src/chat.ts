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
  type: "bar" | "line";
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
  impact: string;
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

export const CHAT_SUGGESTIONS: { intent: Exclude<ChatIntent, "general">; question: string }[] = [
  { intent: "descriptive", question: "Summarize revenue by region last quarter" },
  { intent: "diagnostic", question: "Why did EMEA support tickets spike this week?" },
  { intent: "predictive", question: "Forecast revenue for the next two quarters" },
  { intent: "prescriptive", question: "What should we do to reduce churn this quarter?" },
];

export const INTENT_META: Record<string, { label: string; color: string; bg: string }> = {
  descriptive: { label: "Descriptive agent", color: "var(--ac)", bg: "var(--ac-soft)" },
  diagnostic: { label: "Diagnostic agent", color: "#1d8e9c", bg: "#e3f6f9" },
  predictive: { label: "Predictive agent", color: "#3f6fd6", bg: "#e9eefc" },
  prescriptive: { label: "Prescriptive agent", color: "#0f8a5c", bg: "#e4f6ee" },
  general: { label: "General agent", color: "#64748b", bg: "#f1f5f9" },
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
