import { useState } from "react";
import { useForecast } from "../../api/forecasts";

const HORIZONS = [3, 6, 12] as const;
const HORIZON_LABEL: Record<number, string> = { 3: "next 3 months", 6: "next 6 months", 12: "next 12 months" };

export function ForecastsPage() {
  const [model, setModel] = useState<"OLS" | "Holt-Winters">("Holt-Winters");
  const [horizon, setHorizon] = useState<3 | 6 | 12>(6);
  const { data, isLoading } = useForecast(model, horizon);

  const series = data?.series ?? [];
  const values = series.map((s) => s.value);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const w = 640;
  const h = 220;
  const points = values.map((v, i) => {
    const x = (i / Math.max(values.length - 1, 1)) * w;
    const y = h - ((v - min) / (max - min || 1)) * h;
    return { x, y };
  });
  const linePoints = points.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 22 }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 800, margin: 0 }}>Forecast · Revenue</h1>
          <div style={{ fontSize: 12.5, color: "#9499ad", marginTop: 4 }}>Predictive agent · raw NumPy time-series, 95% confidence intervals</div>
        </div>
        <div style={{ display: "flex", background: "var(--ac-bg-muted)", borderRadius: 10, padding: 3 }}>
          {(["OLS", "Holt-Winters"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setModel(m)}
              style={{ padding: "7px 14px", borderRadius: 8, fontSize: 12.5, fontWeight: 700, background: model === m ? "var(--ac-bg)" : "transparent", color: model === m ? "var(--ac)" : "#71768a" }}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <div style={{ color: "#9499ad" }}>Loading…</div>}

      {data && (
        <>
          <div style={{ background: "var(--ac-bg-muted)", borderRadius: 16, border: "1px solid var(--ac-border)", padding: 18, display: "grid", gridTemplateColumns: "140px 140px 140px 1fr", alignItems: "center", marginBottom: 16 }}>
            <Stat label="PROJECTED" value={data.projected} />
            <Stat label="95% CI" value={`${data.ciLow}–${data.ciHigh}`} />
            <Stat label="GROWTH" value={data.growth} color="#0f8a5c" />
            <div style={{ textAlign: "right" }}>
              <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "#9499ad", marginBottom: 6 }}>HORIZON · {HORIZON_LABEL[horizon].toUpperCase()}</div>
              <div style={{ display: "inline-flex", gap: 6 }}>
                {HORIZONS.map((hval) => (
                  <button
                    key={hval}
                    onClick={() => setHorizon(hval)}
                    style={{ padding: "6px 12px", borderRadius: 20, fontSize: 12, fontWeight: 700, background: horizon === hval ? "var(--ac-soft)" : "var(--ac-bg)", color: horizon === hval ? "var(--ac-deep)" : "#71768a" }}
                  >
                    {hval} mo
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div style={{ background: "var(--ac-bg-muted)", borderRadius: 16, border: "1px solid var(--ac-border)", padding: 18, marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ fontSize: 13.5, fontWeight: 700 }}>
                {model} projection · {HORIZON_LABEL[horizon]}
              </div>
              <div style={{ font: "600 11px 'IBM Plex Mono',monospace", color: "#9499ad" }}>MAPE {data.mape}</div>
            </div>
            <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
              {[0.25, 0.5, 0.75].map((f) => (
                <line key={f} x1={0} x2={w} y1={h * f} y2={h * f} stroke="var(--ac-border)" strokeWidth={1} />
              ))}
              <polyline points={linePoints} fill="none" stroke="#6d4dff" strokeWidth={2} />
              {points.length > 0 && <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r={4} fill="#6d4dff" />}
            </svg>
            <div style={{ display: "flex", gap: 16, fontSize: 11, color: "#9499ad", marginTop: 8 }}>
              <span>● Actual ({series.length} mo)</span>
            </div>
          </div>

          <div style={{ background: "var(--ac-bg-muted)", borderRadius: 16, border: "1px solid var(--ac-border)", padding: 18 }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 12 }}>Top drivers</div>
            {data.topDrivers.map((d) => (
              <div key={d.label} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <span style={{ flex: 1, fontSize: 12.5 }}>{d.label}</span>
                <div style={{ width: 160, height: 7, background: "var(--ac-bg)", borderRadius: 4, overflow: "hidden" }}>
                  <div style={{ width: `${d.pct}%`, height: "100%", background: "var(--ac)", borderRadius: 4 }} />
                </div>
                <span style={{ width: 32, fontSize: 12, fontWeight: 700, textAlign: "right" }}>{d.pct}%</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "#9499ad", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 800, color: color ?? "#1a1d29" }}>{value}</div>
    </div>
  );
}
