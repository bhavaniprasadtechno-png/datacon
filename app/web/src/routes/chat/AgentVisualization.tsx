import type { ChatMessage } from "../../lib/types";
import type { AgentTable, Citation, PrescriptiveAction } from "@datacon/shared-types";
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

function DataTable({ table }: { table: AgentTable }) {
  if (!table.columns.length || !table.rows.length) return null;
  return (
    <div style={{ border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", overflow: "auto", marginTop: 10 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ background: "var(--ac-bg-muted)" }}>
            {table.columns.map((col) => (
              <th
                key={col}
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
              {row.map((cell, j) => (
                <td key={j} style={{ padding: "8px 12px", color: "var(--ac-fg)", whiteSpace: "nowrap" }}>
                  {cell === null ? "—" : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CitationChip({ citation, onOpen }: { citation: Citation; onOpen: (c: Citation) => void }) {
  const label = citation.documentTitle.length > 28 ? `${citation.documentTitle.slice(0, 28)}…` : citation.documentTitle;
  return (
    <button
      onClick={() => onOpen(citation)}
      title={citation.documentTitle}
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
      [{citation.id}] {label}
    </button>
  );
}

function Citations({ items, onOpen }: { items: Citation[]; onOpen: (c: Citation) => void }) {
  return (
    <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac-muted)", marginBottom: 2 }}>
        SOURCES · {items.length} DOCUMENT CHUNK{items.length === 1 ? "" : "S"}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {items.map((c) => (
          <CitationChip key={c.id} citation={c} onOpen={onOpen} />
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
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
      {items.map((a, i) => {
        const usedCitations = (a.citationIds ?? [])
          .map((id) => citations.find((c) => c.id === id))
          .filter((c): c is Citation => Boolean(c));
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
                  <span style={{ fontWeight: 600, color: "var(--ac-fg)" }}>{a.title}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color: EFFORT_COLOR[a.effort] }}>
                    Effort: {a.effort}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--ac-muted)", textTransform: "uppercase", letterSpacing: ".05em" }}>Owner: {a.owner}</span>
                </div>
                <div style={{ fontSize: 12.5, color: "var(--ac-fg)", marginTop: 6 }}>{a.rationale}</div>
                <div style={{ fontSize: 12, color: "var(--ac-muted)", marginTop: 4 }}>
                  <span style={{ fontWeight: 600 }}>Expected impact:</span> {a.expectedImpact}
                </div>
                {usedCitations.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                    {usedCitations.map((c) => (
                      <CitationChip key={c.id} citation={c} onOpen={onOpen} />
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
  if (!message.payload) return null;
  const payload = message.payload;

  return (
    <div style={{ marginTop: 8 }}>
      {payload.correlation && <CorrelationTag text={payload.correlation} />}
      {payload.chart && <AgentChart chart={payload.chart} />}
      {payload.table && <DataTable table={payload.table} />}
      {payload.citations && <Citations items={payload.citations} onOpen={onOpenCitation} />}
      {payload.actions && <RecommendationCards items={payload.actions} citations={payload.citations ?? []} onOpen={onOpenCitation} />}
    </div>
  );
}
