import { Test } from "@nestjs/testing";
import { InsightsService } from "./insights.service";
import { MetricsService } from "../metrics/metrics.service";
import { AiClientService } from "../common/ai-client.service";

describe("InsightsService", () => {
  let service: InsightsService;
  let metrics: jest.Mocked<Pick<MetricsService, "revenueHistory" | "regionRevenue" | "ticketDaily" | "churnSnapshot" | "ticketTableRowCount">>;
  let aiPost: jest.Mock;

  beforeEach(async () => {
    metrics = {
      revenueHistory: jest.fn(),
      regionRevenue: jest.fn(),
      ticketDaily: jest.fn(),
      churnSnapshot: jest.fn(),
      ticketTableRowCount: jest.fn(),
    };
    aiPost = jest.fn();
    const moduleRef = await Test.createTestingModule({
      providers: [
        InsightsService,
        { provide: MetricsService, useValue: metrics },
        { provide: AiClientService, useValue: { client: { post: aiPost } } },
      ],
    }).compile();
    service = moduleRef.get(InsightsService);
  });

  it("returns a no-data state without crashing when nothing is connected", async () => {
    metrics.revenueHistory.mockResolvedValue([]);
    metrics.regionRevenue.mockResolvedValue({ current: [], previous: [] });
    metrics.ticketDaily.mockResolvedValue([]);
    metrics.churnSnapshot.mockResolvedValue(null);
    metrics.ticketTableRowCount.mockResolvedValue(0);

    const result = await service.get();

    expect(result.kpis.revenue.value).toBe("No data");
    expect(result.kpis.revenue.deltaPct).toBe(0);
    expect(result.kpis.churn.value).toBe("No data");
    expect(result.forecast).toBeNull();
    expect(result.attention).toEqual([]);
  });

  it("skips the forecast call when there are fewer than 2 revenue points", async () => {
    metrics.revenueHistory.mockResolvedValue([3.5]);
    metrics.regionRevenue.mockResolvedValue({ current: [{ region: "NA", revenue: 3.5 }], previous: [] });
    metrics.ticketDaily.mockResolvedValue([]);
    metrics.churnSnapshot.mockResolvedValue(null);
    metrics.ticketTableRowCount.mockResolvedValue(0);

    const result = await service.get();

    expect(aiPost).not.toHaveBeenCalled();
    expect(result.forecast).toBeNull();
  });

  it("computes real KPIs when data is connected", async () => {
    metrics.revenueHistory.mockResolvedValue([3.0, 3.5]);
    metrics.regionRevenue.mockResolvedValue({
      current: [{ region: "NA", revenue: 2.0 }],
      previous: [{ region: "NA", revenue: 1.0 }],
    });
    metrics.ticketDaily.mockResolvedValue([
      { date: "2026-07-01", region: "EMEA", count: 40 },
      { date: "2026-07-02", region: "EMEA", count: 80 },
    ]);
    metrics.churnSnapshot.mockResolvedValue({ churnPct: 3.1, prevChurnPct: 3.5, atRiskAccounts: 12 });
    metrics.ticketTableRowCount.mockResolvedValue(120);
    aiPost.mockResolvedValue({ data: { series: [], projected: "$4.00M", ciLow: "$3.80M", ciHigh: "$4.20M" } });

    const result = await service.get();

    expect(result.kpis.revenue.value).toBe("$2.00M");
    expect(result.kpis.revenue.deltaPct).toBe(100);
    expect(result.kpis.churn.value).toBe("3.1%");
    expect(result.forecast).not.toBeNull();
  });
});
