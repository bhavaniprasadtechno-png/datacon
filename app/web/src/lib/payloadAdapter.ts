import type {
  AgentPayload,
  Citation,
  PrescriptiveAction,
  StructuredResponse,
} from "@datacon/shared-types";

/**
 * One shape AgentVisualization renders from, regardless of which analyst
 * produced the message or when it was saved. Analysts migrated onto the
 * new pipeline (descriptive) emit StructuredResponse directly; analysts
 * not yet migrated (diagnostic/predictive/prescriptive/general) and any
 * payload persisted before this change emit the older
 * chart/table/citations/actions/correlation shape. Both normalize here so
 * the renderer never has to branch on payload shape itself.
 */
export interface AdaptedPayload extends StructuredResponse {
  citations: Citation[];
  actions: PrescriptiveAction[];
  correlation: string | null;
}

export function isStructuredResponse(payload: unknown): payload is StructuredResponse {
  return (
    !!payload &&
    typeof payload === "object" &&
    "summary" in payload &&
    ("metrics" in payload || "visualizations" in payload || "tables" in payload)
  );
}

const CHART_VISUALIZATION_TYPES = new Set(["bar", "line", "horizontal_bar"]);

export function isChartVisualization(type: string): boolean {
  return CHART_VISUALIZATION_TYPES.has(type);
}

/** Whether a message's payload (either shape) has anything worth saving as
 * a dashlet — a chart, a table, or prescriptive actions. */
export function hasDashletContent(payload: unknown, fallbackText: string): boolean {
  const adapted = adaptPayload(payload, fallbackText);
  return adapted.visualizations.some((v) => isChartVisualization(v.type)) || adapted.tables.length > 0 || adapted.actions.length > 0;
}

export function adaptPayload(payload: unknown, fallbackText: string): AdaptedPayload {
  if (isStructuredResponse(payload)) {
    // A message can be structured-shape (summary/metrics/...) and still carry
    // the old flat escape-hatch fields alongside it — e.g. Diagnostic's
    // citation-grounded spike answers. Preserve them instead of dropping them.
    const escapeHatch = payload as Partial<AgentPayload>;
    return {
      ...payload,
      citations: escapeHatch.citations ?? [],
      actions: escapeHatch.actions ?? [],
      correlation: escapeHatch.correlation ?? null,
    };
  }

  const old = (payload ?? {}) as Partial<AgentPayload>;

  return {
    summary: { text: fallbackText, confidence: old.confidence ?? "medium" },
    metrics: [],
    insights: [],
    visualizations: old.chart
      ? [{ type: old.chart.type, title: old.chart.title, data: old.chart.data as unknown as Record<string, unknown>[] }]
      : [],
    tables: old.table ? [{ columns: old.table.columns, rows: old.table.rows, collapsed: false }] : [],
    sources: [],
    citations: old.citations ?? [],
    actions: old.actions ?? [],
    correlation: old.correlation ?? null,
  };
}
