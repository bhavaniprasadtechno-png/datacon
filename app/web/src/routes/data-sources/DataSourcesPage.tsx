import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { useDataSources } from "../../api/documents";
import { Button } from "../../components/ui/Button";
import { UploadModal } from "./UploadModal";
import { DataSourceTableModal } from "./DataSourceTableModal";
import type { DataSourceRecord, DocStatus, DocType } from "../../lib/types";

const TYPE_CHIP: Record<DocType, { bg: string; color: string }> = {
  PDF: { bg: "#fdeee9", color: "#c0392b" },
  CSV: { bg: "#e6f7ef", color: "#0f8a5c" },
  MD: { bg: "#e9eefc", color: "#3f6fd6" },
  TXT: { bg: "#f0f1f6", color: "#5a5f72" },
};

const STATUS_META: Record<DocStatus, { label: string; color: string; icon: string; blink?: boolean }> = {
  INDEXED: { label: "Processed", color: "#0f8a5c", icon: "✓" },
  INDEXING: { label: "Processing", color: "#b9743a", icon: "◷", blink: true },
  CHUNKING: { label: "Processing", color: "#b9743a", icon: "◷", blink: true },
  UPLOADING: { label: "Processing", color: "#b9743a", icon: "◷", blink: true },
  FAILED: { label: "Failed", color: "#c0392b", icon: "✕" },
};

function formatSize(row: DataSourceRecord): string {
  if (row.type === "CSV") return row.rowCount != null ? `${row.rowCount.toLocaleString()} rows · ${row.colCount} cols` : "—";
  return row.chunkCount != null ? `${row.chunkCount} chunk${row.chunkCount === 1 ? "" : "s"}` : "—";
}

export function DataSourcesPage() {
  const { caps, user } = useAuth();
  const { data: rows, isLoading, refetch, isFetching } = useDataSources();
  const [showUpload, setShowUpload] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ font: "600 11px 'IBM Plex Mono',monospace", letterSpacing: ".2em", color: "#9489c4", marginBottom: 8 }}>DATA SOURCES</div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 10 }}>
        <h1 style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-.03em", margin: 0 }}>Your governed data inventory.</h1>
        <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
          <Button variant="secondary" onClick={() => refetch()} disabled={isFetching}>
            ↻ Refresh
          </Button>
          {caps.uploadDocs && (
            <Button variant="primary" onClick={() => setShowUpload(true)}>
              ↑ New source
            </Button>
          )}
        </div>
      </div>
      <p style={{ fontSize: 14, color: "#71768a", maxWidth: 680, marginBottom: 24 }}>
        CSV datasets feed the Descriptive agent's structured queries. PDF, TXT &amp; MD files feed the RAG pipeline that the Diagnostic agent cites in its answers.
      </p>

      {!caps.uploadDocs && (
        <div style={{ background: "#f5f6fb", borderRadius: 14, padding: "14px 18px", display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <span style={{ fontSize: 20 }}>🔒</span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700 }}>Uploading is restricted to analysts and admins</div>
            <div style={{ fontSize: 12, color: "#9499ad" }}>You're viewing as {user?.roleName} — switch to Sarah or Tom to add data sources.</div>
          </div>
        </div>
      )}

      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(150px,1.7fr) 66px 150px 120px 170px 100px", padding: "10px 18px", fontSize: 10.5, fontWeight: 700, letterSpacing: ".06em", color: "#9499ad", borderBottom: "1px solid #f0f1f6" }}>
          <span>NAME</span>
          <span>TYPE</span>
          <span>SIZE</span>
          <span>STATUS</span>
          <span>UPLOADED</span>
          <span></span>
        </div>
        {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}
        {rows?.map((row) => {
          const chip = TYPE_CHIP[row.type];
          const status = STATUS_META[row.status];
          return (
            <div key={row.id} style={{ display: "grid", gridTemplateColumns: "minmax(150px,1.7fr) 66px 150px 120px 170px 100px", alignItems: "center", padding: "10px 18px", borderBottom: "1px solid #f5f6fb" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: chip.bg, color: chip.color, display: "flex", alignItems: "center", justifyContent: "center", font: "700 10px 'IBM Plex Mono',monospace", flexShrink: 0 }}>
                  {row.type}
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.title}</div>
                  <div style={{ font: "500 11px 'IBM Plex Mono',monospace", color: "#9499ad" }}>{row.filename}</div>
                </div>
              </div>
              <div style={{ fontSize: 12, color: "#71768a" }}>{row.type}</div>
              <div style={{ fontSize: 12, color: "#71768a" }}>{formatSize(row)}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: status.color, fontWeight: 600 }}>
                <span style={{ animation: status.blink ? "dvblink 1.2s infinite" : "none" }}>{status.icon}</span>
                {status.label}
              </div>
              <div style={{ font: "500 11px 'IBM Plex Mono',monospace", color: "#b0b4c6" }}>
                {new Date(row.createdAt).toLocaleString()}
                <div>by {row.uploadedBy}</div>
              </div>
              <div>
                {row.type === "CSV" && row.status === "INDEXED" && (
                  <button
                    onClick={() => setPreviewId(row.id)}
                    style={{
                      font: "600 11px 'IBM Plex Mono',monospace",
                      color: "#5b3fd6",
                      background: "#efeaff",
                      border: "none",
                      borderRadius: 8,
                      padding: "6px 10px",
                      cursor: "pointer",
                    }}
                  >
                    ⊞ View table
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <UploadModal open={showUpload} onClose={() => setShowUpload(false)} />
      <DataSourceTableModal id={previewId} onClose={() => setPreviewId(null)} />
    </div>
  );
}
