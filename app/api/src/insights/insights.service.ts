import { Injectable } from "@nestjs/common";
import { MetricsService } from "../metrics/metrics.service";
import { AiClientService } from "../common/ai-client.service";

const DEFAULT_MODEL = "Holt-Winters";
const DEFAULT_HORIZON = 6;

@Injectable()
export class InsightsService {
  constructor(
    private readonly metrics: MetricsService,
    private readonly ai: AiClientService,
  ) {}

  async get() {
    const [revenueHistory, regionRevenue, ticketDaily, churnSnapshot, ticketTableRowCount] = await Promise.all([
      this.metrics.revenueHistory(),
      this.metrics.regionRevenue(),
      this.metrics.ticketDaily(),
      this.metrics.churnSnapshot(),
      this.metrics.ticketTableRowCount(),
    ]);

    const totalCurrent = regionRevenue.current.reduce((s, r) => s + r.revenue, 0);
    const totalPrevious = regionRevenue.previous.reduce((s, r) => s + r.revenue, 0);
    const revenueGrowthPct = totalPrevious ? ((totalCurrent - totalPrevious) / totalPrevious) * 100 : 0;

    const baseline = ticketDaily.slice(0, -1);
    const spike = ticketDaily.length ? ticketDaily[ticketDaily.length - 1] : null;
    const baselineAvg = baseline.length ? baseline.reduce((s, d) => s + d.count, 0) / baseline.length : 0;
    const spikePct = spike && baselineAvg ? ((spike.count - baselineAvg) / baselineAvg) * 100 : 0;

    const churnDeltaPp = churnSnapshot ? churnSnapshot.churnPct - churnSnapshot.prevChurnPct : 0;

    const slowest = regionRevenue.current.length
      ? [...regionRevenue.current]
          .map((r) => {
            const prev = regionRevenue.previous.find((p) => p.region === r.region)?.revenue ?? r.revenue;
            return { region: r.region, growthPct: prev ? ((r.revenue - prev) / prev) * 100 : 0 };
          })
          .sort((a, b) => a.growthPct - b.growthPct)[0]
      : null;

    const attention = [
      spike &&
        spikePct > 50 && {
          id: "ticket-spike",
          title: `Ticket spike · ${spike.region}`,
          desc: `+${spikePct.toFixed(0)}% vs 7-day avg · ask why →`,
          tone: "high" as const,
          clickable: true,
          question: `Why did ${spike.region} support tickets spike this week?`,
        },
      churnSnapshot &&
        churnSnapshot.atRiskAccounts > 0 && {
          id: "churn-risk",
          title: `Churn risk · ${churnSnapshot.atRiskAccounts} accounts`,
          desc: "flagged by predictive agent",
          tone: "medium" as const,
          clickable: false,
        },
      slowest && {
        id: "slow-region",
        title: `Slowest growth · ${slowest.region}`,
        desc: `${slowest.growthPct >= 0 ? "+" : ""}${slowest.growthPct.toFixed(1)}% quarter over quarter`,
        tone: "medium" as const,
        clickable: false,
      },
    ].filter(Boolean) as { id: string; title: string; desc: string; tone: "high" | "medium"; clickable: boolean; question?: string }[];

    let forecast: { series: { label: string; value: number }[]; projected: string; ciLow: string; ciHigh: string } | null = null;
    if (revenueHistory.length >= 2) {
      try {
        const res = await this.ai.client.post("/internal/forecast", {
          series: revenueHistory,
          model: DEFAULT_MODEL,
          horizonMonths: DEFAULT_HORIZON,
          regionRevenueCurrent: regionRevenue.current,
          regionRevenuePrevious: regionRevenue.previous,
        });
        forecast = { series: res.data.series, projected: res.data.projected, ciLow: res.data.ciLow, ciHigh: res.data.ciHigh };
      } catch {
        forecast = null;
      }
    }

    return {
      kpis: {
        revenue: { value: totalCurrent ? `$${totalCurrent.toFixed(2)}M` : "No data", deltaPct: revenueGrowthPct },
        churn: { value: churnSnapshot ? `${churnSnapshot.churnPct.toFixed(1)}%` : "No data", deltaPp: churnDeltaPp },
        tickets: { value: ticketTableRowCount.toLocaleString(), deltaPct: spikePct },
        anomalies: {
          count: attention.length,
          highCount: attention.filter((a) => a.tone === "high").length,
          mediumCount: attention.filter((a) => a.tone === "medium").length,
        },
      },
      forecast,
      attention,
    };
  }
}
