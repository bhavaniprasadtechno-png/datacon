import { Injectable } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";
import { AiClientService } from "../common/ai-client.service";

type MetricsQueryResult = { ok: boolean; columns: string[]; rows: (string | number | boolean | null)[][]; message: string };

@Injectable()
export class MetricsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly ai: AiClientService,
  ) {}

  private async query(question: string): Promise<MetricsQueryResult> {
    try {
      const res = await this.ai.client.post("/internal/metrics/query", { question });
      return res.data as MetricsQueryResult;
    } catch {
      return { ok: false, columns: [], rows: [], message: "Metrics query failed." };
    }
  }

  private colIndex(columns: string[], ...keywords: string[]): number {
    const lower = columns.map((c) => c.toLowerCase());
    for (const kw of keywords) {
      const i = lower.findIndex((c) => c.includes(kw));
      if (i >= 0) return i;
    }
    return -1;
  }

  async revenueHistory(): Promise<number[]> {
    const result = await this.query("Total revenue for each month, ordered chronologically, with columns for month and revenue.");
    if (!result.ok) return [];
    const revenueIdx = this.colIndex(result.columns, "revenue", "amount", "total");
    if (revenueIdx < 0) return [];
    return result.rows.map((r) => Number(r[revenueIdx]) || 0);
  }

  async regionRevenue(): Promise<{ current: { region: string; revenue: number }[]; previous: { region: string; revenue: number }[] }> {
    const empty = { current: [], previous: [] };
    const result = await this.query(
      "Total revenue grouped by period and region, with columns for period (quarter or month), region and revenue.",
    );
    if (!result.ok) return empty;

    const periodIdx = this.colIndex(result.columns, "period", "quarter", "month");
    const regionIdx = this.colIndex(result.columns, "region");
    const revenueIdx = this.colIndex(result.columns, "revenue", "amount", "total");
    if (periodIdx < 0 || regionIdx < 0 || revenueIdx < 0) return empty;

    const periods = [...new Set(result.rows.map((r) => String(r[periodIdx])))].sort();
    if (periods.length === 0) return empty;
    const currentPeriod = periods[periods.length - 1];
    const previousPeriod = periods.length > 1 ? periods[periods.length - 2] : null;

    const toPoints = (period: string) =>
      result.rows
        .filter((r) => String(r[periodIdx]) === period)
        .map((r) => ({ region: String(r[regionIdx]), revenue: Number(r[revenueIdx]) || 0 }));

    return { current: toPoints(currentPeriod), previous: previousPeriod ? toPoints(previousPeriod) : [] };
  }

  async ticketDaily(): Promise<{ date: string; region: string; count: number }[]> {
    const result = await this.query(
      "Support ticket count grouped by day and region, ordered chronologically, with columns for date, region and count.",
    );
    if (!result.ok) return [];
    const dateIdx = this.colIndex(result.columns, "date", "day");
    const regionIdx = this.colIndex(result.columns, "region");
    const countIdx = this.colIndex(result.columns, "count", "tickets");
    if (dateIdx < 0 || regionIdx < 0 || countIdx < 0) return [];
    return result.rows.map((r) => ({ date: String(r[dateIdx]), region: String(r[regionIdx]), count: Number(r[countIdx]) || 0 }));
  }

  async churnSnapshot(): Promise<{ churnPct: number; prevChurnPct: number; atRiskAccounts: number } | null> {
    const result = await this.query(
      "The single most recent churn rate percentage, the previous period's churn rate percentage, and the number of at-risk accounts.",
    );
    if (!result.ok || result.rows.length === 0) return null;

    const churnIdx = this.colIndex(result.columns, "churnpct", "churn_pct", "churn");
    const prevIdx = this.colIndex(result.columns, "prevchurn", "prev_churn", "previous");
    const atRiskIdx = this.colIndex(result.columns, "atrisk", "at_risk", "risk");
    if (churnIdx < 0) return null;

    const row = result.rows[0];
    return {
      churnPct: Number(row[churnIdx]) || 0,
      prevChurnPct: prevIdx >= 0 ? Number(row[prevIdx]) || 0 : 0,
      atRiskAccounts: atRiskIdx >= 0 ? Number(row[atRiskIdx]) || 0 : 0,
    };
  }

  async ticketTableRowCount(): Promise<number> {
    const row = await this.prisma.unifiedDataset.findFirst({ where: { name: "tickets" } });
    return row?.rowCount ?? 0;
  }
}
