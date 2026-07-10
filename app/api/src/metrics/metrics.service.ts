import { Injectable } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";

function previousQuarter(quarter: string): string {
  const [year, q] = quarter.split("-Q").map(Number);
  return q === 1 ? `${year - 1}-Q4` : `${year}-Q${q - 1}`;
}

@Injectable()
export class MetricsService {
  constructor(private readonly prisma: PrismaService) {}

  async revenueHistory(): Promise<number[]> {
    const rows = await this.prisma.revenueMetric.findMany({ orderBy: { month: "asc" } });
    return rows.map((r) => r.revenue);
  }

  async regionRevenue(): Promise<{ current: { region: string; revenue: number }[]; previous: { region: string; revenue: number }[] }> {
    const rows = await this.prisma.regionRevenue.findMany();
    const quarters = Array.from(new Set(rows.map((r) => String(r.quarter)))) as string[];
    quarters.sort();
    const currentQuarter: string | null = quarters[quarters.length - 1] ?? null;
    const prevQuarter = currentQuarter ? previousQuarter(currentQuarter) : null;
    return {
      current: rows.filter((r) => r.quarter === currentQuarter).map((r) => ({ region: r.region, revenue: r.revenue })),
      previous: rows.filter((r) => r.quarter === prevQuarter).map((r) => ({ region: r.region, revenue: r.revenue })),
    };
  }

  async ticketDaily(): Promise<{ date: string; region: string; count: number }[]> {
    const rows = await this.prisma.ticketDaily.findMany({ orderBy: { date: "asc" } });
    return rows.map((r) => ({ date: r.date.toISOString().slice(0, 10), region: r.region, count: r.count }));
  }

  async churnSnapshot(): Promise<{ churnPct: number; prevChurnPct: number; atRiskAccounts: number }> {
    const row = await this.prisma.churnSnapshot.findFirst({ orderBy: { asOf: "desc" } });
    return { churnPct: row?.churnPct ?? 0, prevChurnPct: row?.prevChurnPct ?? 0, atRiskAccounts: row?.atRiskAccounts ?? 0 };
  }

  async ticketTableRowCount(): Promise<number> {
    const row = await this.prisma.unifiedDataset.findFirst({ where: { name: "tickets" } });
    return row?.rowCount ?? 0;
  }

  async topIncidentTitle(): Promise<string | null> {
    const row = await this.prisma.dataSource.findFirst({ where: { type: "PDF" }, orderBy: { createdAt: "asc" } });
    return row?.title ?? null;
  }

  /** Bundles everything the AI service's agents need for a chat turn or a forecast call. */
  async chatContext(model: string, horizonMonths: number) {
    const [revenueHistory, regionRevenue, ticketDaily, churnSnapshot, topIncidentTitle] = await Promise.all([
      this.revenueHistory(),
      this.regionRevenue(),
      this.ticketDaily(),
      this.churnSnapshot(),
      this.topIncidentTitle(),
    ]);
    return { revenueHistory, regionRevenue, ticketDaily, churnSnapshot, topIncidentTitle, model, horizonMonths };
  }
}
