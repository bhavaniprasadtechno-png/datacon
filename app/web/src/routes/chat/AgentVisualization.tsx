import { useState } from "react";
import type { ChatMessage } from "../../lib/types";
import type { AgentTable, Citation, Insight, Metric, PrescriptiveAction, Source, StructuredTable } from "@datacon/shared-types";
import { adaptPayload, isChartVisualization } from "../../lib/payloadAdapter";
import { AgentChart } from "./AgentChart";

function CorrelationTag({ text }: { text: string }) {
  return (
    <div
      style={{
        display: "inline-block",
        marginTop: 8,
        background: "var(--ac-soft)",
        color: "var(--ac-deep)",
        fontSize: 11,
        fontWeight: 600,
        padding: "4px 10px",
        borderRadius: "var(--radius-sm)",
      }}
    >
      {text}
    </div>
  );
}

const METRIC_FORMAT: Record<Metric["format"], { prefix: string; suffix: string }> = {
  currency: { prefix: "$", suffix: "" },
  number: { prefix: "", suffix: "" },
  percentage: { prefix: "", suffix: "%" },
  text: { prefix: "", suffix: "" },
};

function formatMetricValue(metric: Metric): string {
  const value = typeof metric.value === "number" ? metric.value.toLocaleString() : String(metric.value);
  const { prefix, suffix } = METRIC_FORMAT[metric.format];
  return `${prefix}${value}${suffix}`;
}

function MetricCards({ metrics }: { metrics: Metric[] }) {
  if (!metrics.length) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 10 }}>
      {metrics.map((m) => (
        <div
          key={m.id}
          style={{
            border: "1px solid var(--ac-border)",
            borderRadius: "var(--radius-lg)",
            padding: "10px 14px",
            minWidth: 100,
            background: "var(--ac-bg-muted)",
          }}
        >
          <div style={{ font: "600 9px 'IBM Plex Mono',monospace", letterSpacing: ".08em", color: "var(--ac-muted)", marginBottom: 2 }}>
            {m.label.toUpperCase()}
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--ac-fg)" }}>{formatMetricValue(m)}</div>
        </div>
      ))}
    </div>
  );
}

const INSIGHT_STYLE: Record<Insight["type"], { icon: string; color: string }> = {
  positive: { icon: "✓", color: "#0f8a5c" },
  attention: { icon: "⚠", color: "#a3730c" },
  neutral: { icon: "•", color: "var(--ac-muted)" },
};

function InsightList({ insights }: { insights: Insight[] }) {
  if (!insights.length) return null;
  return (
    <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac-muted)" }}>KEY INSIGHTS</div>
      {insights.map((insight, i) => (
        <div key={i} style={{ display: "flex", gap: 6, fontSize: 12.5, color: "var(--ac-fg)" }}>
          <span style={{ color: INSIGHT_STYLE[insight.type].color }}>{INSIGHT_STYLE[insight.type].icon}</span>
          <span>{insight.text}</span>
        </div>
      ))}
    </div>
  );
}

function DataTable({ table }: { table: AgentTable | StructuredTable }) {
  if (!table || !Array.isArray(table.columns) || !Array.isArray(table.rows) || !table.columns.length || !table.rows.length) return null;
  return (
    <div style={{ border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", overflow: "auto", marginTop: 10 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ background: "var(--ac-bg-muted)" }}>
            {table.columns.map((col, idx) => (
              <th
                key={col || idx}
                style={{
                  textAlign: "left",
                  padding: "8px 12px",
                  fontSize: 10,
                  fontWeight: 700,
                  color: "var(--ac-muted)",
                  fontFamily: "'IBM Plex Mono',monospace",
                  whiteSpace: "nowrap",
                }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i} style={{ borderTop: "1px solid var(--ac-border)" }}>
              {Array.isArray(row) && row.map((cell, j) => (
                <td key={j} style={{ padding: "8px 12px", color: "var(--ac-fg)", whiteSpace: "nowrap" }}>
                  {cell === null || cell === undefined ? "—" : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecordsDisclosure({ table }: { table: StructuredTable }) {
  const [open, setOpen] = useState(!table.collapsed);
  if (!table.columns.length || !table.rows.length) return null;
  if (!table.collapsed) return <DataTable table={table} />;
  return (
    <div style={{ marginTop: 10 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          padding: 0,
          font: "600 12px inherit",
          color: "var(--ac)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 4,
        }}
      >
        <span style={{ transform: open ? "rotate(90deg)" : "none", display: "inline-block", transition: "transform 0.15s" }}>▸</span>
        {open ? "Hide underlying records" : "View underlying records"}
      </button>
      {open && <DataTable table={table} />}
    </div>
  );
}

function SourcesLine({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <div style={{ marginTop: 10, fontSize: 11, color: "var(--ac-muted)" }}>
      Sources: {sources.map((s) => s.dataset).join(", ")}
    </div>
  );
}

function CitationChip({ citation, onOpen }: { citation: Citation; onOpen: (c: Citation) => void }) {
  if (!citation) return null;
  const docTitle = citation.documentTitle || "Document";
  const label = docTitle.length > 28 ? `${docTitle.slice(0, 28)}…` : docTitle;
  return (
    <button
      onClick={() => onOpen(citation)}
      title={docTitle}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 11,
        fontWeight: 600,
        color: "var(--ac-deep)",
        background: "var(--ac-soft)",
        border: "1px solid var(--ac-border)",
        borderRadius: "var(--radius-sm)",
        padding: "3px 8px",
        cursor: "pointer",
      }}
    >
      [{citation.id || "?"}] {label}
    </button>
  );
}

function Citations({ items, onOpen }: { items: Citation[]; onOpen: (c: Citation) => void }) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac-muted)", marginBottom: 2 }}>
        SOURCES · {items.length} DOCUMENT CHUNK{items.length === 1 ? "" : "S"}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {items.map((c) => (
          <CitationChip key={c.id || Math.random()} citation={c} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}

const EFFORT_COLOR: Record<PrescriptiveAction["effort"], string> = {
  Low: "#0f8a5c",
  Medium: "#a3730c",
  High: "#cf202f",
};

function RecommendationCards({ items, citations, onOpen }: { items: PrescriptiveAction[]; citations: Citation[]; onOpen: (c: Citation) => void }) {
  if (!Array.isArray(items) || !items.length) return null;
  const safeCitations = Array.isArray(citations) ? citations : [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
      {items.map((a, i) => {
        if (!a) return null;
        const usedCitations = (a.citationIds ?? [])
          .map((id) => safeCitations.find((c) => c && c.id === id))
          .filter((c): c is Citation => Boolean(c));
        const color = (a.effort && EFFORT_COLOR[a.effort]) ? EFFORT_COLOR[a.effort] : "#a3730c";
        return (
          <div key={i} style={{ border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 14 }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  background: "var(--ac)",
                  color: "#fff",
                  fontSize: 11,
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                {i + 1}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600, color: "var(--ac-fg)" }}>{a.title || (a as any).action || "Action"}</span>
                  {a.effort && (
                    <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color }}>
                      Effort: {a.effort}
                    </span>
                  )}
                  {a.owner && (
                    <span style={{ fontSize: 10, color: "var(--ac-muted)", textTransform: "uppercase", letterSpacing: ".05em" }}>Owner: {a.owner}</span>
                  )}
                </div>
                <div style={{ fontSize: 12.5, color: "var(--ac-fg)", marginTop: 6 }}>{a.rationale}</div>
                {a.expectedImpact && (
                  <div style={{ fontSize: 12, color: "var(--ac-muted)", marginTop: 4 }}>
                    <span style={{ fontWeight: 600 }}>Expected impact:</span> {a.expectedImpact}
                  </div>
                )}
                {usedCitations.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                    {usedCitations.map((c) => (
                      <CitationChip key={c.id || Math.random()} citation={c} onOpen={onOpen} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function AgentVisualization({ message, onOpenCitation }: { message: ChatMessage; onOpenCitation: (citation: Citation) => void }) {
  if (!message || !message.payload || typeof message.payload !== "object") return null;
  const adapted = adaptPayload(message.payload, message.text);
  const chartViz = adapted.visualizations.find((v) => isChartVisualization(v.type));

  return (
    <div style={{ marginTop: 8 }}>
      {adapted.correlation && <CorrelationTag text={adapted.correlation} />}
      <MetricCards metrics={adapted.metrics} />
      {chartViz && (
        <AgentChart chart={{ type: chartViz.type as "bar" | "line" | "horizontal_bar", title: chartViz.title ?? "", data: chartViz.data as any }} />
      )}
      <InsightList insights={adapted.insights} />
      {adapted.tables.map((t, i) => (
        <RecordsDisclosure key={i} table={t} />
      ))}
      <Citations items={adapted.citations} onOpen={onOpenCitation} />
      <RecommendationCards items={adapted.actions} citations={adapted.citations} onOpen={onOpenCitation} />
      <SourcesLine sources={adapted.sources} />
    </div>
  );
}
