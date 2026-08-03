import { useState } from "react";
import { useAuth } from "../../stores/useAuthStore";
import { useDataSources, useDeleteDataSource } from "../../api/documents";
import { Button } from "../../components/ui/Button";
import { useConfirm } from "../../stores/useConfirmStore";
import { UploadModal } from "./UploadModal";
import { DataSourceTableModal } from "./DataSourceTableModal";
import type { DataSourceRecord, DocStatus, DocType } from "../../lib/types";
import { RefreshCw, Upload, Lock, Eye, Trash2, Check, Loader2, XCircle } from "lucide-react";
import { TableRowSkeleton } from "../../components/ui/Skeleton";

const TYPE_CHIP: Record<DocType, { bg: string; color: string }> = {
  PDF: { bg: "#fdeee9", color: "#c0392b" },
  CSV: { bg: "#e6f7ef", color: "#0f8a5c" },
  MD: { bg: "#e9eefc", color: "#3f6fd6" },
  TXT: { bg: "#f0f1f6", color: "#5a5f72" },
};

const STATUS_META: Record<DocStatus, { label: string; color: string; icon: React.ReactNode; blink?: boolean }> = {
  INDEXED: { label: "Processed", color: "#0f8a5c", icon: <Check size={14} /> },
  INDEXING: { label: "Processing", color: "#b9743a", icon: <Loader2 size={14} style={{ animation: "dvspin 1s linear infinite" }} />, blink: true },
  CHUNKING: { label: "Processing", color: "#b9743a", icon: <Loader2 size={14} style={{ animation: "dvspin 1s linear infinite" }} />, blink: true },
  UPLOADING: { label: "Processing", color: "#b9743a", icon: <Loader2 size={14} style={{ animation: "dvspin 1s linear infinite" }} />, blink: true },
  FAILED: { label: "Failed", color: "#c0392b", icon: <XCircle size={14} /> },
};

function formatSize(row: DataSourceRecord): string {
  if (row.type === "CSV") return row.rowCount != null ? `${row.rowCount.toLocaleString()} rows · ${row.colCount} cols` : "—";
  return row.chunkCount != null ? `${row.chunkCount} chunk${row.chunkCount === 1 ? "" : "s"}` : "—";
}

export function DataSourcesPage() {
  const { caps, user } = useAuth();
  const { data: rows, isLoading, refetch, isFetching } = useDataSources();
  const deleteDataSource = useDeleteDataSource();
  const [showUpload, setShowUpload] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const confirm = useConfirm();

  const removeRow = async (row: DataSourceRecord) => {
    const ok = await confirm({
      title: "Delete data source",
      body: `Delete "${row.title}"? This can't be undone.`,
      label: "Delete",
      tone: "danger",
    });
    if (!ok) return;
    deleteDataSource.mutate(row.id);
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ font: "600 11px 'IBM Plex Mono',monospace", letterSpacing: ".2em", color: "var(--ac-muted)", marginBottom: 8 }}>DATA SOURCES</div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 10 }}>
        <h1 style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-.03em", margin: 0 }}>Your governed data inventory.</h1>
        <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
          <Button variant="secondary" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw size={14} /> Refresh
          </Button>
          {caps.uploadDocs && (
            <Button variant="primary" onClick={() => setShowUpload(true)}>
              <Upload size={14} /> New source
            </Button>
          )}
        </div>
      </div>
      <p style={{ fontSize: 14, color: "var(--ac-muted)", maxWidth: 680, marginBottom: 24 }}>
        CSV datasets feed the Descriptive agent's structured queries. PDF, TXT &amp; MD files feed the RAG pipeline that the Diagnostic agent cites in its answers.
      </p>

      {!caps.uploadDocs && (
        <div style={{ background: "var(--ac-bg-muted)", borderRadius: "var(--radius-md)", border: "1px solid var(--ac-border)", padding: "14px 18px", display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <Lock size={18} style={{ color: "var(--ac-muted)", flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: 13, fontWeight: 700 }}>Uploading is restricted to analysts and admins</div>
            <div style={{ fontSize: 12, color: "var(--ac-muted)" }}>You're viewing as {user?.kind === "org_member" ? user.roleName : ""} — ask an admin to grant upload access to add data sources.</div>
          </div>
        </div>
      )}

      <div style={{ background: "#fff", borderRadius: "var(--radius-lg)", border: "1px solid var(--ac-border)", overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(150px,1.7fr) 66px 150px 120px 170px 100px", padding: "10px 18px", fontSize: 10.5, fontWeight: 700, letterSpacing: ".06em", color: "var(--ac-muted)", borderBottom: "1px solid var(--ac-border)" }}>
          <span>NAME</span>
          <span>TYPE</span>
          <span>SIZE</span>
          <span>STATUS</span>
          <span>UPLOADED</span>
          <span>ACTIONS</span>
        </div>
        {isLoading ? (
          <>
            <TableRowSkeleton gridCols="minmax(150px,1.7fr) 66px 150px 120px 170px 100px" />
            <TableRowSkeleton gridCols="minmax(150px,1.7fr) 66px 150px 120px 170px 100px" />
            <TableRowSkeleton gridCols="minmax(150px,1.7fr) 66px 150px 120px 170px 100px" />
            <TableRowSkeleton gridCols="minmax(150px,1.7fr) 66px 150px 120px 170px 100px" />
            <TableRowSkeleton gridCols="minmax(150px,1.7fr) 66px 150px 120px 170px 100px" />
          </>
        ) : (
          rows?.map((row) => {
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
                    <div style={{ fontSize: 11, color: "#9499ad", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.filename}</div>
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: 11, fontWeight: 700, color: chip.color }}>{row.type}</span>
                </div>
                <div style={{ fontSize: 12.5, color: "#5a5f72" }}>{formatSize(row)}</div>
                <div>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, color: status.color, fontWeight: 600 }}>
                    <span style={{ animation: status.blink ? "dvblink 1.2s infinite" : "none", display: "flex", alignItems: "center" }}>
                      {status.icon}
                    </span>
                    {status.label}
                  </span>
                </div>
                <div style={{ fontSize: 12.5, color: "#9499ad" }}>
                  {new Date(row.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  {row.type === "CSV" ? (
                    <button onClick={() => setPreviewId(row.id)} style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12, textAlign: "left", display: "flex", alignItems: "center", gap: 4, padding: 0 }}>
                      <Eye size={13} /> View
                    </button>
                  ) : (
                    <span style={{ color: "#d4d7e2", fontSize: 12, display: "flex", alignItems: "center", gap: 4 }}>
                      <Eye size={13} /> View
                    </span>
                  )}
                  {caps.uploadDocs ? (
                    <button onClick={() => removeRow(row)} style={{ color: "#c0392b", fontWeight: 700, fontSize: 12, textAlign: "left", display: "flex", alignItems: "center", gap: 4, padding: 0 }}>
                      <Trash2 size={13} /> Delete
                    </button>
                  ) : (
                    <span style={{ color: "#d4d7e2", fontSize: 12, display: "flex", alignItems: "center", gap: 4 }}>
                      <Trash2 size={13} /> Delete
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      <UploadModal open={showUpload} onClose={() => setShowUpload(false)} />
      <DataSourceTableModal id={previewId} onClose={() => setPreviewId(null)} />
    </div>
  );
}
