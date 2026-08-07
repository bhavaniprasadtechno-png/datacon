import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { X } from "lucide-react";
import type { Citation } from "@datacon/shared-types";
import { useDashboard, useDeleteDashlet } from "../../api/dashboards";
import { AgentVisualization } from "../chat/AgentVisualization";
import { CitationDrawer } from "../../components/common/CitationDrawer";
import type { ChatMessage } from "../../lib/types";

export function DashboardDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data, isLoading } = useDashboard(id);
  const deleteDashlet = useDeleteDashlet();
  const [openCitation, setOpenCitation] = useState<Citation | null>(null);

  return (
    <div style={{ padding: 32, maxWidth: 1180, margin: "0 auto" }}>
      <button onClick={() => navigate("/insights?tab=dashboards")} style={{ fontSize: 12.5, fontWeight: 700, color: "var(--ac-muted)", marginBottom: 12 }}>
        ← All dashboards
      </button>
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 20 }}>{data?.name ?? (isLoading ? "" : "Dashboard")}</h1>

      {!isLoading && data && data.dashlets.length === 0 && <div style={{ color: "var(--ac-muted)", fontSize: 13.5 }}>No dashlets yet.</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 16 }}>
        {data?.dashlets.map((d) => {
          const message: ChatMessage = { id: d.id, role: "agent", intent: d.intent, text: d.text, payload: d.payload, vote: 0 };
          return (
            <div key={d.id} style={{ background: "#fff", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 18 }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{d.title}</div>
                  <div style={{ fontSize: 12, color: "var(--ac-muted)", marginTop: 2 }}>{d.text}</div>
                </div>
                <button
                  onClick={() => deleteDashlet.mutate({ dashboardId: id, dashletId: d.id })}
                  style={{ color: "var(--ac-muted)", flexShrink: 0 }}
                  aria-label="Remove dashlet"
                >
                  <X size={16} />
                </button>
              </div>
              <AgentVisualization message={message} onOpenCitation={setOpenCitation} />
            </div>
          );
        })}
      </div>

      <CitationDrawer citation={openCitation} onClose={() => setOpenCitation(null)} />
    </div>
  );
}
