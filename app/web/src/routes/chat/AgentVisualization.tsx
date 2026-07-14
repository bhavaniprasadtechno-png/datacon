import { useState } from "react";
import type { ChatMessage } from "../../lib/types";

// The new pipeline payload shape emitted by the AI service. Kept loose
// because the details bag is intentionally schema-lite — we render whatever
// the pipeline actually attached, and hide the panel if empty.
interface PipelineDetails {
  retriever?: {
    db_facts?: Array<{ field: string; source: string; shape: string }>;
    doc_facts?: Array<{ id: number; documentTitle: string; filename: string; chunkIndex: number; snippet: string }>;
    sources?: string[];
    coverage?: { db_fields_present?: string[]; db_fields_missing?: string[] };
  };
  analysts?: Array<{ intent: string; payload: Record<string, unknown> }>;
  validator?: {
    conflicts?: Array<{ note: string }>;
    gaps?: string[];
    freshness_notes?: string[];
    has_issues?: boolean;
  };
  intents_selected?: string[];
}

export function AgentVisualization({ message }: { message: ChatMessage }) {
  if (!message.payload) return null;

  // The pipeline attaches `details` alongside any per-analyst payload shape.
  // Cast is safe because the responder's payload shape is opaque to
  // shared-types; the runtime check on `details` is the source of truth.
  const details = (message.payload as unknown as { details?: PipelineDetails }).details;

  return (
    <>
      {renderInlineVisualization(message)}
      {details ? <PipelineDetailsPanel details={details} /> : null}
    </>
  );
}

// --- Expandable "Show reasoning" panel --------------------------------------
function PipelineDetailsPanel({ details }: { details: PipelineDetails }) {
  const [open, setOpen] = useState(false);
  const sources = details.retriever?.sources ?? [];
  const conflicts = details.validator?.conflicts ?? [];
  const gaps = details.validator?.gaps ?? [];
  const intents = details.intents_selected ?? [];
  const docs = details.retriever?.doc_facts ?? [];
  const dbFacts = details.retriever?.db_facts ?? [];

  if (!sources.length && !conflicts.length && !gaps.length && !intents.length && !docs.length) return null;

  return (
    <div style={{ marginTop: 12, borderTop: "1px dashed #e9eaf2", paddingTop: 10 }}>
      {/* Compact source strip — always visible, no click required */}
      {sources.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: conflicts.length || gaps.length ? 8 : 0 }}>
          {sources.slice(0, 6).map((s, i) => (
            <span
              key={i}
              data-testid="responder-source-chip"
              style={{
                font: "600 10px 'IBM Plex Mono',monospace",
                color: s.startsWith("Doc:") ? "#1d8e9c" : "#5b3fd6",
                background: s.startsWith("Doc:") ? "#e3f6f9" : "#efeaff",
                padding: "3px 8px",
                borderRadius: 6,
              }}
            >
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Conflict / gap surfacing — always visible when present */}
      {conflicts.length > 0 && (
        <div data-testid="responder-conflicts" style={{ background: "#fff3ed", border: "1px solid #f8c9a6", borderRadius: 8, padding: "8px 10px", fontSize: 12, color: "#8a4400", marginBottom: 6 }}>
          <strong>⚠ Data conflicts flagged ({conflicts.length}):</strong>
          <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
            {conflicts.map((c, i) => (
              <li key={i}>{c.note}</li>
            ))}
          </ul>
        </div>
      )}
      {gaps.length > 0 && (
        <div data-testid="responder-gaps" style={{ background: "#f9f4ff", border: "1px solid #d9c5f8", borderRadius: 8, padding: "8px 10px", fontSize: 12, color: "#5b3fd6", marginBottom: 6 }}>
          <strong>⚠ Data gaps:</strong>
          <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
            {gaps.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Collapsed reasoning toggle */}
      <button
        data-testid="show-reasoning-toggle"
        onClick={() => setOpen((v) => !v)}
        style={{
          font: "600 10.5px 'IBM Plex Mono',monospace",
          color: "#9499ad",
          background: "transparent",
          border: "none",
          padding: 0,
          marginTop: conflicts.length || gaps.length ? 4 : 0,
          cursor: "pointer",
        }}
      >
        {open ? "▾ Hide reasoning" : "▸ Show reasoning"}
      </button>

      {open && (
        <div data-testid="reasoning-panel" style={{ marginTop: 8, background: "#f7f8fc", border: "1px solid #e9eaf2", borderRadius: 10, padding: 12, fontSize: 12, lineHeight: 1.55, color: "#3a3d4f" }}>
          {intents.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ font: "700 9.5px 'IBM Plex Mono',monospace", color: "#9499ad", marginBottom: 4 }}>
                ANALYST MODES INVOKED
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {intents.map((i) => (
                  <span key={i} style={{ font: "600 10px 'IBM Plex Mono',monospace", background: "#eceafc", color: "#5b3fd6", padding: "2px 8px", borderRadius: 6 }}>
                    {i}
                  </span>
                ))}
              </div>
            </div>
          )}
          {dbFacts.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ font: "700 9.5px 'IBM Plex Mono',monospace", color: "#9499ad", marginBottom: 4 }}>
                DATABASE FIELDS RETRIEVED
              </div>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {dbFacts.map((f, i) => (
                  <li key={i}>
                    <code style={{ font: "500 11px 'IBM Plex Mono',monospace" }}>
                      {f.source}.{f.field}
                    </code>
                    <span style={{ color: "#9499ad" }}> ({f.shape})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {docs.length > 0 && (
            <div>
              <div style={{ font: "700 9.5px 'IBM Plex Mono',monospace", color: "#9499ad", marginBottom: 4 }}>
                DOCUMENT SNIPPETS RETRIEVED
              </div>
              {docs.map((d) => (
                <div key={d.id} style={{ borderLeft: "2px solid #2bb8c4", paddingLeft: 10, marginBottom: 6 }}>
                  <div style={{ fontWeight: 700 }}>{d.documentTitle}</div>
                  <div style={{ font: "500 10.5px 'IBM Plex Mono',monospace", color: "#9499ad" }}>
                    chunk {d.chunkIndex} · {d.filename}
                  </div>
                  <div style={{ fontStyle: "italic", color: "#5a5f72" }}>"{d.snippet.slice(0, 240)}"</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// --- Legacy inline visualizations (chart / table / citations) --------------
// Preserved from the earlier design so cards still render for analytical
// payloads that carry the classic shapes (bars / series / actions / citations).
function renderInlineVisualization(message: ChatMessage) {
  if (!message.payload) return null;

  if (message.intent === "diagnostic" && "citations" in message.payload) {
    const p = message.payload as unknown as { citations: { id: number; documentTitle: string; filename: string; chunkIndex: number; snippet: string }[]; correlation?: string };
    return (
      <div style={{ marginTop: 10 }}>
        {p.correlation && (
          <div style={{ display: "inline-block", background: "#e3f6f9", color: "#1d8e9c", fontSize: 11, fontWeight: 700, padding: "4px 10px", borderRadius: 20, marginBottom: 10 }}>
            {p.correlation}
          </div>
        )}
        <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "#9499ad", marginBottom: 8 }}>
          SOURCES · {p.citations.length} DOCUMENT CHUNK{p.citations.length === 1 ? "" : "S"}
        </div>
        {p.citations.map((c) => (
          <div key={c.id} style={{ borderLeft: "2px solid #2bb8c4", paddingLeft: 10, marginBottom: 10 }}>
            <div style={{ fontSize: 12.5, fontWeight: 700 }}>{c.documentTitle}</div>
            <div style={{ font: "500 10.5px 'IBM Plex Mono',monospace", color: "#9499ad", margin: "2px 0" }}>
              chunk {c.chunkIndex} · {c.filename}
            </div>
            <div style={{ fontSize: 12, color: "#5a5f72", fontStyle: "italic" }}>"{c.snippet}"</div>
          </div>
        ))}
      </div>
    );
  }

  if (message.intent === "predictive" && "series" in message.payload) {
    const p = message.payload as unknown as { series: { label: string; value: number }[]; model: string; projected: string; ciLow: string; ciHigh: string; growth: string };
    const values = p.series.map((s) => s.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const w = 320;
    const h = 90;
    const points = values.map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / (max - min || 1)) * h;
      return `${x},${y}`;
    });
    return (
      <div style={{ background: "#f7faff", border: "1px solid #e6eefc", borderRadius: 12, padding: 14, marginTop: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "#3f6fd6" }}>FORECAST · {p.model.toUpperCase()}</span>
          <span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: "#9499ad" }}>95% CI</span>
        </div>
        <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block", marginBottom: 10 }}>
          <polyline points={points.join(" ")} fill="none" stroke="#6d4dff" strokeWidth={2} />
        </svg>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, textAlign: "center" }}>
          <Stat label="PROJECTED" value={p.projected} />
          <Stat label="95% CI" value={`${p.ciLow}–${p.ciHigh}`} />
          <Stat label="GROWTH" value={p.growth} color="#0f8a5c" />
        </div>
      </div>
    );
  }

  if (message.intent === "prescriptive" && "actions" in message.payload) {
    const p = message.payload as unknown as { actions: { title: string; impact: string; effort: string; owner: string }[] };
    return (
      <div style={{ border: "1px solid #e4f6ee", borderRadius: 12, overflow: "hidden", marginTop: 10 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 82px 64px 82px", background: "#eef9f3", padding: "8px 12px", fontSize: 10, fontWeight: 700, color: "#0f8a5c" }}>
          <span>RECOMMENDED ACTION</span>
          <span>IMPACT</span>
          <span>EFFORT</span>
          <span>OWNER</span>
        </div>
        {p.actions.map((a, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 82px 64px 82px", padding: "9px 12px", fontSize: 12, borderTop: "1px solid #f0f1f6", alignItems: "center" }}>
            <span>{a.title}</span>
            <span style={{ color: "#0f8a5c", fontWeight: 700 }}>{a.impact}</span>
            <span style={{ color: a.effort === "Low" ? "#0f8a5c" : "#b9743a", fontWeight: 600 }}>{a.effort}</span>
            <span style={{ color: "#71768a" }}>{a.owner}</span>
          </div>
        ))}
      </div>
    );
  }

  return null;
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ font: "600 9px 'IBM Plex Mono',monospace", color: "#9499ad", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 800, color: color ?? "#1a1d29" }}>{value}</div>
    </div>
  );
}
