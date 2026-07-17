import { useNavigate } from "react-router-dom";
import { useAuth } from "../../stores/useAuthStore";
import { useInsights } from "../../api/insights";
import { useConnectors } from "../../api/connectors";

const TONE_STYLE = {
  high: { bg: "#fdeee9", dot: "#e2603f" },
  medium: { bg: "var(--ac-soft)", dot: "var(--ac)" },
};

export function InsightsPage() {
  const { user } = useAuth();
  const { data, isLoading } = useInsights();
  const { data: connectors } = useConnectors();
  const navigate = useNavigate();

  const liveSyncs = connectors?.filter((c) => c.status === "SYNCED" || c.status === "SYNCING").length ?? 0;
  const todayLabel = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  const greeting = user?.roleName === "Viewer" ? "Welcome back" : "Good morning";

  const askAbout = (question: string) => {
    if (question) sessionStorage.setItem("datacon:pendingQuestion", question);
    navigate("/chat");
  };

  if (isLoading || !data) {
    return <div style={{ padding: 32, color: "#9499ad" }}>Loading…</div>;
  }

  const series = data.forecast?.series ?? [];
  const values = series.map((s) => s.value);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const w = 500;
  const h = 150;
  const points = values.map((v, i) => {
    const x = (i / Math.max(values.length - 1, 1)) * w;
    const y = h - ((v - min) / (max - min || 1)) * h;
    return `${x},${y}`;
  });

  return (
    <div style={{ padding: 32, maxWidth: 1180, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 22 }}>
        <div>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "#9499ad" }}>{todayLabel}</div>
          <h1 style={{ fontSize: 25, fontWeight: 800, margin: "2px 0 0" }}>
            {greeting}, {user?.name.split(" ")[0]}
          </h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--ac-soft)", color: "var(--ac-deep)", padding: "6px 14px", borderRadius: 20, fontSize: 12, fontWeight: 700 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--ac)", animation: "dvblink 1.6s infinite" }} />
          {liveSyncs} live sync{liveSyncs === 1 ? "" : "s"}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 20 }}>
        <KpiCard label="Total revenue" value={data.kpis.revenue.value} deltaLabel={`${data.kpis.revenue.deltaPct >= 0 ? "↑" : "↓"} ${Math.abs(data.kpis.revenue.deltaPct).toFixed(1)}%`} good={data.kpis.revenue.deltaPct >= 0} />
        <KpiCard label="Net churn" value={data.kpis.churn.value} deltaLabel={`${data.kpis.churn.deltaPp <= 0 ? "↓" : "↑"} ${Math.abs(data.kpis.churn.deltaPp).toFixed(1)}pp`} good={data.kpis.churn.deltaPp <= 0} />
        <KpiCard label="Daily tickets" value={data.kpis.tickets.value} deltaLabel={`${data.kpis.tickets.deltaPct >= 0 ? "↑" : "↓"} ${Math.abs(data.kpis.tickets.deltaPct).toFixed(0)}%`} good={data.kpis.tickets.deltaPct <= 0} />
        <div style={{ background: "linear-gradient(140deg,#1a1d29,#34304f)", borderRadius: 16, padding: "17px 18px", color: "#fff" }}>
          <div style={{ fontSize: 11.5, color: "#c3c7d6", marginBottom: 8 }}>Active anomalies</div>
          <div style={{ fontSize: 26, fontWeight: 800, marginBottom: 8 }}>{data.kpis.anomalies.count}</div>
          <span style={{ fontSize: 10.5, background: "rgba(255,255,255,.14)", padding: "3px 9px", borderRadius: 20 }}>
            {data.kpis.anomalies.highCount} high · {data.kpis.anomalies.mediumCount} medium
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr", gap: 16, marginBottom: 20 }}>
        <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
            <div style={{ fontSize: 13.5, fontWeight: 700 }}>Revenue &amp; forecast</div>
            <button onClick={() => navigate("/forecasts")} style={{ fontSize: 12, color: "var(--ac)", fontWeight: 700 }}>
              Open forecast →
            </button>
          </div>
          <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
            <polyline points={points.join(" ")} fill="none" stroke="var(--ac)" strokeWidth={2.5} />
          </svg>
          <div style={{ display: "flex", gap: 16, fontSize: 11, color: "#9499ad", marginTop: 8 }}>
            <span>● Actual</span>
            <span>● Forecast (95% CI)</span>
          </div>
        </div>

        <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", padding: 18 }}>
          <div style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 12 }}>Needs your attention</div>
          {data.attention.map((a) => {
            const tone = TONE_STYLE[a.tone];
            const content = (
              <div style={{ display: "flex", gap: 10, padding: "9px 10px", borderRadius: 10, background: a.clickable ? tone.bg : "transparent", marginBottom: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: tone.dot, marginTop: 4, flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 12.5, fontWeight: 700 }}>{a.title}</div>
                  <div style={{ fontSize: 11.5, color: "#9499ad" }}>{a.desc}</div>
                </div>
              </div>
            );
            return a.clickable ? (
              <button key={a.id} onClick={() => askAbout(a.question!)} style={{ width: "100%", textAlign: "left" }}>
                {content}
              </button>
            ) : (
              <div key={a.id}>{content}</div>
            );
          })}
        </div>
      </div>

      <button
        onClick={() => askAbout("")}
        style={{ width: "100%", display: "flex", alignItems: "center", gap: 12, background: "#fff", border: "1px solid #e9eaf2", borderRadius: 16, padding: "14px 18px", cursor: "text" }}
      >
        <span style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--ac-logo)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13 }}>✦</span>
        <span style={{ flex: 1, textAlign: "left", fontSize: 13.5, color: "#9499ad" }}>Ask Datacon anything about your business…</span>
        <span style={{ background: "var(--ac-grad)", color: "#fff", fontWeight: 700, fontSize: 12.5, padding: "8px 16px", borderRadius: 10 }}>Ask ✦</span>
      </button>
    </div>
  );
}

function KpiCard({ label, value, deltaLabel, good }: { label: string; value: string; deltaLabel: string; good: boolean }) {
  return (
    <div className="dvfu" style={{ background: "#fff", borderRadius: 16, padding: "17px 18px", border: "1px solid #e9eaf2" }}>
      <div style={{ fontSize: 11.5, color: "#9499ad", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 8 }}>{value}</div>
      <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 20, color: good ? "#13a06b" : "#d4654a", background: good ? "#e6f7ef" : "#fdeee9" }}>{deltaLabel}</span>
    </div>
  );
}
