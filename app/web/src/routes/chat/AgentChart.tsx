import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AgentChart as AgentChartData } from "@datacon/shared-types";

function formatMillions(value: number): string {
  return `$${value.toFixed(2)}M`;
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ font: "600 9px 'IBM Plex Mono',monospace", color: "var(--ac-muted)", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 700, color: color ?? "var(--ac-fg)" }}>{value}</div>
    </div>
  );
}

export function AgentChart({ chart }: { chart: AgentChartData }) {
  if (!chart.data.length) return null;

  if (chart.type === "bar") {
    return (
      <div style={{ background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 14, marginTop: 10 }}>
        <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac)", marginBottom: 8 }}>
          {chart.title.toUpperCase()}
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chart.data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--ac-border)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--ac-muted)" />
            <YAxis tick={{ fontSize: 11 }} stroke="var(--ac-muted)" width={40} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Bar dataKey="value" fill="var(--ac)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // Line chart: history points followed by one appended forecast point
  // carrying lower/upper — the stat row below reads straight off that last
  // pair of points instead of duplicating formatted fields on the payload.
  const last = chart.data[chart.data.length - 1];
  const prev = chart.data.length > 1 ? chart.data[chart.data.length - 2] : undefined;
  const hasForecast = last.lower !== undefined && last.upper !== undefined;
  const growthPct = hasForecast && prev ? ((last.value - prev.value) / prev.value) * 100 : undefined;

  // recharts Areas fill from the chart's zero baseline independently unless
  // stacked with a shared stackId. To render a true lower..upper band, stack
  // an invisible floor (lower) with a visible delta (band = upper - lower)
  // on top, so the visible fill spans exactly [lower, upper].
  const bandData = chart.data.map((d) => ({
    ...d,
    band: d.lower !== undefined && d.upper !== undefined ? d.upper - d.lower : undefined,
  }));

  return (
    <div style={{ background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 14, marginTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac)" }}>{chart.title.toUpperCase()}</span>
        {hasForecast && <span style={{ font: "600 10px 'IBM Plex Mono',monospace", color: "var(--ac-muted)" }}>95% CI</span>}
      </div>
      <ResponsiveContainer width="100%" height={140}>
        {hasForecast ? (
          <ComposedChart data={bandData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--ac-border)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--ac-muted)" />
            <YAxis tick={{ fontSize: 11 }} stroke="var(--ac-muted)" width={40} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Area type="monotone" dataKey="lower" stackId="ci" stroke="none" fill="var(--ac)" fillOpacity={0} legendType="none" />
            <Area type="monotone" dataKey="band" stackId="ci" stroke="none" fill="var(--ac)" fillOpacity={0.12} legendType="none" />
            <Line type="monotone" dataKey="value" stroke="var(--ac)" strokeWidth={2} dot={{ r: 3 }} />
          </ComposedChart>
        ) : (
          <LineChart data={chart.data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--ac-border)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--ac-muted)" />
            <YAxis tick={{ fontSize: 11 }} stroke="var(--ac-muted)" width={40} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Line type="monotone" dataKey="value" stroke="var(--ac)" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        )}
      </ResponsiveContainer>
      {hasForecast && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, textAlign: "center", marginTop: 10 }}>
          <Stat label="PROJECTED" value={formatMillions(last.value)} />
          <Stat label="95% CI" value={`${formatMillions(last.lower as number)}–${formatMillions(last.upper as number)}`} />
          {growthPct !== undefined && (
            <Stat label="GROWTH" value={`${growthPct >= 0 ? "+" : ""}${growthPct.toFixed(1)}%`} color="#0f8a5c" />
          )}
        </div>
      )}
    </div>
  );
}
