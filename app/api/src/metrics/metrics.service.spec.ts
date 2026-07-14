import { Test } from "@nestjs/testing";
import { MetricsService } from "./metrics.service";
import { PrismaService } from "../prisma/prisma.service";
import { AiClientService } from "../common/ai-client.service";

describe("MetricsService", () => {
  let service: MetricsService;
  let aiPost: jest.Mock;

  beforeEach(async () => {
    aiPost = jest.fn();
    const moduleRef = await Test.createTestingModule({
      providers: [
        MetricsService,
        {
          provide: PrismaService,
          useValue: { unifiedDataset: { findFirst: jest.fn().mockResolvedValue(null) }, dataSource: { findFirst: jest.fn().mockResolvedValue(null) } },
        },
        { provide: AiClientService, useValue: { client: { post: aiPost } } },
      ],
    }).compile();
    service = moduleRef.get(MetricsService);
  });

  it("returns an empty array when the query engine has no revenue data", async () => {
    aiPost.mockResolvedValue({ data: { ok: false, columns: [], rows: [], message: "No data is connected yet." } });
    expect(await service.revenueHistory()).toEqual([]);
  });

  it("parses a revenue-by-month result into a chronological number series", async () => {
    aiPost.mockResolvedValue({
      data: { ok: true, columns: ["month", "total_revenue"], rows: [["2026-01", 3.05], ["2026-02", 3.11]], message: "ok" },
    });
    expect(await service.revenueHistory()).toEqual([3.05, 3.11]);
  });

  it("returns empty current/previous when the query engine finds no region revenue", async () => {
    aiPost.mockResolvedValue({ data: { ok: false, columns: [], rows: [], message: "No data is connected yet." } });
    expect(await service.regionRevenue()).toEqual({ current: [], previous: [] });
  });

  it("splits region revenue into the latest and prior period", async () => {
    aiPost.mockResolvedValue({
      data: {
        ok: true,
        columns: ["quarter", "region", "revenue"],
        rows: [
          ["2026-Q1", "NA", 1.82],
          ["2026-Q2", "NA", 1.94],
        ],
        message: "ok",
      },
    });
    expect(await service.regionRevenue()).toEqual({
      current: [{ region: "NA", revenue: 1.94 }],
      previous: [{ region: "NA", revenue: 1.82 }],
    });
  });

  it("returns null churn data when the query engine has nothing connected", async () => {
    aiPost.mockResolvedValue({ data: { ok: false, columns: [], rows: [], message: "No data is connected yet." } });
    expect(await service.churnSnapshot()).toBeNull();
  });

  it("parses a churn snapshot row", async () => {
    aiPost.mockResolvedValue({
      data: { ok: true, columns: ["churn_pct", "prev_churn_pct", "at_risk_accounts"], rows: [[3.1, 3.5, 12]], message: "ok" },
    });
    expect(await service.churnSnapshot()).toEqual({ churnPct: 3.1, prevChurnPct: 3.5, atRiskAccounts: 12 });
  });

  it("swallows a failed HTTP call and returns the same empty shape as an explicit non-answer", async () => {
    aiPost.mockRejectedValue(new Error("network error"));
    expect(await service.revenueHistory()).toEqual([]);
  });
});
