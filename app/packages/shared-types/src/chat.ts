export type ChatIntent = "descriptive" | "diagnostic" | "predictive" | "prescriptive";

export interface DescriptivePayload {
  columns: string[];
  rows: (string | number | boolean | null)[][];
}

export interface Citation {
  id: number;
  documentTitle: string;
  filename: string;
  chunkIndex: number;
  snippet: string;
}

export interface DiagnosticPayload {
  correlation?: string;
  citations: Citation[];
}

export interface ForecastPoint {
  label: string;
  value: number;
  lower?: number;
  upper?: number;
}

export interface PredictivePayload {
  model: "OLS" | "Holt-Winters";
  projected: string;
  ciLow: string;
  ciHigh: string;
  growth: string;
  mape: string;
  series: ForecastPoint[];
}

export interface PrescriptiveAction {
  title: string;
  impact: string;
  effort: "Low" | "Medium" | "High";
  owner: string;
}

export interface PrescriptivePayload {
  actions: PrescriptiveAction[];
}

export type AgentPayload =
  | ({ intent: "descriptive" } & DescriptivePayload)
  | ({ intent: "diagnostic" } & DiagnosticPayload)
  | ({ intent: "predictive" } & PredictivePayload)
  | ({ intent: "prescriptive" } & PrescriptivePayload);

export const CHAT_SUGGESTIONS: { intent: ChatIntent; question: string }[] = [
  { intent: "descriptive", question: "Summarize revenue by region last quarter" },
  { intent: "diagnostic", question: "Why did EMEA support tickets spike this week?" },
  { intent: "predictive", question: "Forecast revenue for the next two quarters" },
  { intent: "prescriptive", question: "What should we do to reduce churn this quarter?" },
];

export const INTENT_META: Record<ChatIntent, { label: string; color: string; bg: string }> = {
  descriptive: { label: "Descriptive agent", color: "var(--ac)", bg: "var(--ac-soft)" },
  diagnostic: { label: "Diagnostic agent", color: "#1d8e9c", bg: "#e3f6f9" },
  predictive: { label: "Predictive agent", color: "#3f6fd6", bg: "#e9eefc" },
  prescriptive: { label: "Prescriptive agent", color: "#0f8a5c", bg: "#e4f6ee" },
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
  { id: "gemini/gemini-2.5-flash", label: "Gemini 2.5 Flash", description: "Fast, low-cost default" },
  { id: "gemini/gemini-3-flash-preview", label: "Gemini 3 Flash Preview", description: "Newer, more capable" },
  { id: "gemini/gemma-4-31b-it", label: "Gemma 4 31B", description: "Open-weight reasoning model" },
];
