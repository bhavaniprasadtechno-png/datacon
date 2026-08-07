import { useNavigate } from "react-router-dom";
import { LayoutDashboard } from "lucide-react";
import { useDashboards } from "../../api/dashboards";

export function DashboardsList() {
  const { data: dashboards = [], isLoading } = useDashboards();
  const navigate = useNavigate();

  if (isLoading) return null;

  if (dashboards.length === 0) {
    return (
      <div style={{ background: "#fff", border: "1px dashed var(--ac-border)", borderRadius: 16, padding: 48, textAlign: "center" }}>
        <div style={{ width: 44, height: 44, borderRadius: "var(--radius-lg)", background: "var(--ac-soft)", color: "var(--ac)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px" }}>
          <LayoutDashboard size={22} />
        </div>
        <div style={{ fontSize: 15, fontWeight: 800, marginBottom: 6 }}>No dashboards yet</div>
        <div style={{ fontSize: 12.5, color: "var(--ac-muted)", maxWidth: 360, margin: "0 auto 18px" }}>
          Ask Datacon a question in chat, then hit "Add to dashboard" on any insight to start building one.
        </div>
        <button
          onClick={() => navigate("/chat")}
          style={{ background: "var(--ac)", color: "#fff", fontWeight: 700, fontSize: 13, padding: "9px 18px", borderRadius: "var(--radius-sm)" }}
        >
          Go to chat →
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14 }}>
      {dashboards.map((d) => (
        <button
          key={d.id}
          onClick={() => navigate(`/insights/dashboards/${d.id}`)}
          style={{ textAlign: "left", background: "#fff", border: "1px solid var(--ac-border)", borderRadius: 16, padding: 18 }}
        >
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: "var(--ac)", marginBottom: 10 }} />
          <div style={{ fontSize: 14.5, fontWeight: 800 }}>{d.name}</div>
          <div style={{ fontSize: 12, color: "var(--ac-muted)", marginTop: 4 }}>{d.dashletCount} dashlet{d.dashletCount === 1 ? "" : "s"}</div>
        </button>
      ))}
    </div>
  );
}
