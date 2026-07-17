import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../stores/useAuthStore";
import { useCatalog, useConnectors, useDeleteConnector, useSyncConnector } from "../../api/connectors";
import { useToast } from "../../stores/useToastStore";
import { useConfirm } from "../../stores/useConfirmStore";
import { Button } from "../../components/ui/Button";
import { STATUS_META, TYPE_STYLE, timeAgo } from "../../lib/connectorMeta";
import { apiErrorMessage } from "../../api/client";
import { AddConnectorModal } from "./AddConnectorModal";
import { TablePreviewModal } from "./TablePreviewModal";
import type { Connector } from "../../lib/types";
import { Lock, Trash2, Plus, AlertTriangle } from "lucide-react";

export function ConnectorsPage() {
  const { caps } = useAuth();
  const { data: connectors, isLoading } = useConnectors();
  const { data: catalog } = useCatalog();
  const { addToast } = useToast();
  const confirm = useConfirm();
  const syncConnector = useSyncConnector();
  const deleteConnector = useDeleteConnector();
  const navigate = useNavigate();

  const [showAdd, setShowAdd] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);

  const blocked = () => addToast({ icon: <Lock size={16} />, accent: "#b9743a", title: "View-only access", desc: "Ask an admin (Tom) to change data connections." });

  const askAboutTable = (question: string) => {
    sessionStorage.setItem("datacon:pendingQuestion", question);
    setPreviewId(null);
    navigate("/chat");
  };

  const sync = async (c: Connector) => {
    if (!caps.manageConnectors) return blocked();
    try {
      await syncConnector.mutateAsync(c.id);
    } catch (err) {
      addToast({ icon: <AlertTriangle size={16} />, accent: "#e2603f", title: "Sync failed", desc: apiErrorMessage(err) });
    }
  };

  const remove = async (c: Connector) => {
    if (!caps.manageConnectors) return blocked();
    const ok = await confirm({ title: `Remove ${c.name}?`, body: "Its encrypted secrets and cached tables will be permanently deleted.", label: "Remove connector", tone: "danger" });
    if (!ok) return;
    try {
      await deleteConnector.mutateAsync(c.id);
      addToast({ icon: <Trash2 size={16} />, accent: "#e2603f", title: "Connector removed", desc: "Encrypted secrets were purged" });
    } catch (err) {
      addToast({ icon: <AlertTriangle size={16} />, accent: "#e2603f", title: "Couldn't remove connector", desc: apiErrorMessage(err) });
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 22 }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 800, margin: 0 }}>Data connectors</h1>
          <div style={{ fontSize: 12.5, color: "var(--ac-muted)", marginTop: 4 }}>Seven engines supported · secrets encrypted with Fernet-equivalent AES-256-GCM at rest</div>
        </div>
        {caps.manageConnectors ? (
          <Button variant="primary" onClick={() => setShowAdd(true)}>
            <Plus size={14} /> Add connector
          </Button>
        ) : (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--ac-muted)", background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", padding: "7px 12px", borderRadius: "var(--radius-pill)" }}>
            <Lock size={12} /> View-only · ask an admin to change connections
          </span>
        )}
      </div>

      {isLoading && <div style={{ color: "#9499ad" }}>Loading…</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 16, marginBottom: 30 }}>
        {connectors?.map((c) => {
          const style = TYPE_STYLE[c.engine];
          const status = STATUS_META[c.status];
          return (
            <div key={c.id} style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", padding: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 42, height: 42, borderRadius: 12, background: style.bg, color: style.color, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 16, flexShrink: 0 }}>
                  {style.letter}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{c.name}</div>
                  <div style={{ fontSize: 11.5, color: "#9499ad" }}>
                    {c.engine} · {c.syncInterval}
                  </div>
                </div>
                <span style={{ display: "flex", alignItems: "center", gap: 5, font: "600 10px 'IBM Plex Mono',monospace", color: status.color, background: status.bg, padding: "4px 9px", borderRadius: 20, whiteSpace: "nowrap" }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: status.dot, animation: c.status === "SYNCING" ? "dvblink 1.2s infinite" : "none" }} />
                  {status.label}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--ac-border)", fontSize: 11.5, color: "var(--ac-muted)" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                  <Lock size={12} /> secrets *** · last sync {timeAgo(c.lastSyncedAt)}
                </span>
                {caps.manageConnectors ? (
                  <div style={{ display: "flex", gap: 12 }}>
                    <button onClick={() => sync(c)} style={{ color: "var(--ac)", fontWeight: 700 }}>
                      Sync now
                    </button>
                    <button onClick={() => remove(c)} style={{ color: "#c0392b", fontWeight: 700 }}>
                      Delete
                    </button>
                  </div>
                ) : (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Lock size={12} /> Locked</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <span style={{ font: "600 10.5px 'IBM Plex Mono',monospace", letterSpacing: ".16em", color: "var(--ac-muted)" }}>UNIFIED DATA STORE · CATALOG</span>
        <div style={{ flex: 1, height: 1, background: "var(--ac-border)" }} />
        <span style={{ fontSize: 11.5, color: "var(--ac-muted)" }}>{catalog?.length ?? 0} tables imported</span>
      </div>

      <div style={{ background: "#fff", borderRadius: "var(--radius-lg)", border: "1px solid var(--ac-border)", overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1.2fr 160px 120px 92px", padding: "10px 18px", fontSize: 10.5, fontWeight: 700, letterSpacing: ".06em", color: "var(--ac-muted)", borderBottom: "1px solid var(--ac-border)" }}>
          <span>TABLE</span>
          <span>SOURCE</span>
          <span>SHAPE</span>
          <span>STATUS</span>
          <span>ACTION</span>
        </div>
        {catalog?.map((row) => {
          const style = TYPE_STYLE[row.connectorEngine];
          const status = STATUS_META[row.status === "syncing" ? "SYNCING" : row.status === "error" ? "ERROR" : "SYNCED"];
          return (
            <div key={row.id} style={{ display: "grid", gridTemplateColumns: "1.4fr 1.2fr 160px 120px 92px", alignItems: "center", padding: "10px 18px", borderBottom: "1px solid var(--ac-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                <div style={{ width: 26, height: 26, borderRadius: 7, background: style.bg, color: style.color, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 11, flexShrink: 0 }}>
                  {style.letter}
                </div>
                <span style={{ font: "600 12.5px 'IBM Plex Mono',monospace" }}>{row.name}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--ac-muted)" }}>{row.connectorName}</div>
              <div style={{ fontSize: 12, color: "var(--ac-muted)" }}>
                {row.columns.length} cols · {row.rowCount.toLocaleString()} rows
              </div>
              <div>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, color: status.color }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: status.dot }} />
                  {status.label}
                </span>
              </div>
              <button onClick={() => setPreviewId(row.id)} style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12, textAlign: "left" }}>
                View table
              </button>
            </div>
          );
        })}
      </div>

      <AddConnectorModal open={showAdd} onClose={() => setShowAdd(false)} />
      <TablePreviewModal id={previewId} onClose={() => setPreviewId(null)} onAsk={askAboutTable} />
    </div>
  );
}
