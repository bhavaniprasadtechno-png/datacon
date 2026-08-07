import { useEffect, useState } from "react";
import { LayoutDashboard } from "lucide-react";
import { Modal, ModalHeader, ModalFooter } from "../../components/ui/Modal";
import { useToast } from "../../stores/useToastStore";
import { apiErrorMessage } from "../../api/client";
import { useDashboards, useSaveDashboard, type DashletIntent } from "../../api/dashboards";
import type { ChatPayload } from "../../lib/types";

type VisualInclude = "both" | "chart" | "table";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  text: string;
  intent: DashletIntent;
  payload: ChatPayload;
}

export function SaveDashboardModal({ open, onClose, title, text, intent, payload }: Props) {
  const { data: dashboards = [] } = useDashboards();
  const saveDashboard = useSaveDashboard();
  const { addToast } = useToast();
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [name, setName] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [include, setInclude] = useState<VisualInclude>("both");

  const hasChart = !!payload.chart;
  const hasTable = !!payload.table;

  useEffect(() => {
    if (!open) return;
    setMode("new");
    setName("");
    setSelectedId(null);
    setInclude("both");
  }, [open]);

  // Dashboards usually aren't loaded yet the instant the modal opens, so the
  // default selection is filled in here once the list arrives — separate
  // from the reset above so a user's manual pick is never overwritten.
  useEffect(() => {
    if (open && selectedId === null && dashboards.length > 0) {
      setSelectedId(dashboards[0].id);
    }
  }, [open, dashboards, selectedId]);

  if (!open) return null;

  const canSave = mode === "new" ? name.trim().length > 0 : !!selectedId;

  const save = async () => {
    try {
      const targetName = mode === "existing" ? dashboards.find((d) => d.id === selectedId)?.name : name.trim();
      const scopedPayload: ChatPayload = {
        ...payload,
        chart: include === "table" ? undefined : payload.chart,
        table: include === "chart" ? undefined : payload.table,
      };
      await saveDashboard.mutateAsync({
        dashboardId: mode === "existing" ? selectedId! : undefined,
        name: mode === "new" ? name.trim() : undefined,
        title,
        text,
        intent,
        payload: scopedPayload,
      });
      addToast({
        icon: <LayoutDashboard size={16} />,
        accent: "var(--ac)",
        title: mode === "new" ? "Dashboard created" : "Added to dashboard",
        desc: `${targetName ?? "Your dashboard"} now includes this insight as a dashlet.`,
      });
      onClose();
    } catch (err) {
      addToast({ icon: <LayoutDashboard size={16} />, accent: "#e2603f", title: "Couldn't save", desc: apiErrorMessage(err) });
    }
  };

  return (
    <Modal open={open} onClose={onClose} width={460}>
      <ModalHeader title="Save as dashboard" onClose={onClose} />
      <div style={{ fontSize: 12.5, color: "var(--ac-muted)", marginTop: -8, marginBottom: 16 }}>Add "{title}" as a dashlet</div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 20 }}>
        <button
          onClick={() => setMode("new")}
          style={{
            padding: "10px 0",
            borderRadius: "var(--radius-sm)",
            border: `1px solid ${mode === "new" ? "var(--ac)" : "var(--ac-border)"}`,
            background: mode === "new" ? "var(--ac-soft)" : "#fff",
            color: mode === "new" ? "var(--ac-deep)" : "var(--ac-fg)",
            fontSize: 13,
            fontWeight: 700,
          }}
        >
          New dashboard
        </button>
        <button
          onClick={() => dashboards.length > 0 && setMode("existing")}
          disabled={dashboards.length === 0}
          style={{
            padding: "10px 0",
            borderRadius: "var(--radius-sm)",
            border: `1px solid ${mode === "existing" ? "var(--ac)" : "var(--ac-border)"}`,
            background: mode === "existing" ? "var(--ac-soft)" : "#fff",
            color: mode === "existing" ? "var(--ac-deep)" : "var(--ac-fg)",
            fontSize: 13,
            fontWeight: 700,
            opacity: dashboards.length === 0 ? 0.5 : 1,
          }}
        >
          Existing dashboard
        </button>
      </div>

      {/* ModalFooter is sticky with a -mb-5 offset that eats up to 20px of
          whatever margin directly precedes it, so this wrapper's marginBottom
          must be 20px more than the gap we actually want — see SaveDashboardModal
          spacing note. Keeping all variable content inside one wrapper means the
          footer gap stays correct regardless of which block renders last. */}
      <div style={{ marginBottom: 40 }}>
        {mode === "new" ? (
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: "var(--ac-muted)", marginBottom: 6 }}>Dashboard name</div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Quick Commerce Growth"
              style={{ width: "100%", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-sm)", padding: "10px 12px", fontSize: 13.5 }}
            />
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20, maxHeight: 220, overflowY: "auto" }}>
            {dashboards.map((d) => (
              <button
                key={d.id}
                onClick={() => setSelectedId(d.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  textAlign: "left",
                  padding: "10px 12px",
                  borderRadius: "var(--radius-sm)",
                  border: `1px solid ${selectedId === d.id ? "var(--ac)" : "var(--ac-border)"}`,
                  background: selectedId === d.id ? "var(--ac-soft)" : "#fff",
                  fontSize: 13,
                  fontWeight: 700,
                  color: selectedId === d.id ? "var(--ac-deep)" : "var(--ac-fg)",
                }}
              >
                <span>{d.name}</span>
                <span style={{ fontWeight: 500, color: "var(--ac-muted)", flexShrink: 0 }}>
                  {d.dashletCount} dashlet{d.dashletCount === 1 ? "" : "s"}
                </span>
              </button>
            ))}
          </div>
        )}

        {hasChart && hasTable && (
          <div>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: "var(--ac-muted)", marginBottom: 6 }}>Include</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
              {(["both", "chart", "table"] as const).map((opt) => (
                <button
                  key={opt}
                  onClick={() => setInclude(opt)}
                  style={{
                    padding: "8px 0",
                    borderRadius: "var(--radius-sm)",
                    border: `1px solid ${include === opt ? "var(--ac)" : "var(--ac-border)"}`,
                    background: include === opt ? "var(--ac-soft)" : "#fff",
                    color: include === opt ? "var(--ac-deep)" : "var(--ac-fg)",
                    fontSize: 12.5,
                    fontWeight: 700,
                    textTransform: "capitalize",
                  }}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <ModalFooter>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <button onClick={onClose} style={{ padding: "10px 0", borderRadius: "var(--radius-sm)", border: "1px solid var(--ac-border)", background: "#fff", fontSize: 13.5, fontWeight: 700 }}>
            Cancel
          </button>
          <button
            onClick={save}
            disabled={!canSave || saveDashboard.isPending}
            style={{
              padding: "10px 0",
              borderRadius: "var(--radius-sm)",
              border: "none",
              background: "var(--ac)",
              color: "#fff",
              fontSize: 13.5,
              fontWeight: 700,
              opacity: !canSave || saveDashboard.isPending ? 0.6 : 1,
            }}
          >
            Save
          </button>
        </div>
      </ModalFooter>
    </Modal>
  );
}
