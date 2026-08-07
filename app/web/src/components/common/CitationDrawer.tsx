import type { Citation } from "@datacon/shared-types";

export function CitationDrawer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  if (!citation) return null;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40, background: "rgba(0,0,0,0.3)" }}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ position: "absolute", right: 0, top: 0, height: "100%", width: "min(480px, 100%)", background: "#fff", borderLeft: "1px solid var(--ac-border)", padding: 24, overflowY: "auto" }}
      >
        <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac-muted)" }}>SOURCE CITATION</div>
        <div style={{ fontSize: 19, fontWeight: 800, marginTop: 8 }}>{citation.documentTitle}</div>
        <div style={{ font: "500 11px 'IBM Plex Mono',monospace", color: "var(--ac-muted)", marginTop: 4 }}>
          {citation.filename} · chunk {citation.chunkIndex}
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--ac-fg)", marginTop: 16, background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-sm)", padding: 14, whiteSpace: "pre-wrap" }}>
          {citation.snippet}
        </div>
        <button onClick={onClose} style={{ marginTop: 20, padding: "8px 14px", borderRadius: "var(--radius-sm)", background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", fontSize: 12.5, fontWeight: 600 }}>
          Close
        </button>
      </div>
    </div>
  );
}
