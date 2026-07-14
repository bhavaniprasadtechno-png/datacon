import { Test } from "@nestjs/testing";
import { ForecastsController } from "./forecasts.controller";
import { MetricsService } from "../metrics/metrics.service";
import { AiClientService } from "../common/ai-client.service";

describe("ForecastsController", () => {
  let controller: ForecastsController;
  let metrics: jest.Mocked<Pick<MetricsService, "revenueHistory" | "regionRevenue">>;
  let aiPost: jest.Mock;

  beforeEach(async () => {
    metrics = {
      revenueHistory: jest.fn(),
      regionRevenue: jest.fn(),
    };
    aiPost = jest.fn();
    const moduleRef = await Test.createTestingModule({
      controllers: [ForecastsController],
      providers: [
        { provide: MetricsService, useValue: metrics },
        { provide: AiClientService, useValue: { client: { post: aiPost } } },
      ],
    }).compile();
    controller = moduleRef.get(ForecastsController);
  });

  it("returns a no-data shape without calling the AI service when revenue history is empty", async () => {
    metrics.revenueHistory.mockResolvedValue([]);
    metrics.regionRevenue.mockResolvedValue({ current: [], previous: [] });

    const result = await controller.get();

    expect(aiPost).not.toHaveBeenCalled();
    expect(result).toEqual({
      model: "Holt-Winters",
      horizon: 6,
      projected: "No data",
      ciLow: "No data",
      ciHigh: "No data",
      growth: "No data",
      mape: "No data",
      series: [],
      topDrivers: [],
    });
  });

  it("returns a no-data shape without calling the AI service when revenue history has a single point", async () => {
    metrics.revenueHistory.mockResolvedValue([3.5]);
    metrics.regionRevenue.mockResolvedValue({ current: [{ region: "NA", revenue: 3.5 }], previous: [] });

    const result = await controller.get("OLS", "12");

    expect(aiPost).not.toHaveBeenCalled();
    expect(result).toEqual({
      model: "OLS",
      horizon: 12,
      projected: "No data",
      ciLow: "No data",
      ciHigh: "No data",
      growth: "No data",
      mape: "No data",
      series: [],
      topDrivers: [],
    });
  });

  it("calls /internal/forecast and returns the AI response when there are 2+ revenue points", async () => {
    metrics.revenueHistory.mockResolvedValue([3.0, 3.5]);
    metrics.regionRevenue.mockResolvedValue({
      current: [{ region: "NA", revenue: 2.0 }],
      previous: [{ region: "NA", revenue: 1.0 }],
    });
    aiPost.mockResolvedValue({
      data: {
        projected: "$4.28M",
        ciLow: "$4.00M",
        ciHigh: "$4.56M",
        growth: "+12.0%",
        mape: "5.0%",
        series: [{ label: "m0", value: 3.0 }],
        topDrivers: [{ label: "NA revenue growth", pct: 100 }],
      },
    });

    const result = await controller.get();

    expect(aiPost).toHaveBeenCalledWith("/internal/forecast", {
      series: [3.0, 3.5],
      model: "Holt-Winters",
      horizonMonths: 6,
      regionRevenueCurrent: [{ region: "NA", revenue: 2.0 }],
      regionRevenuePrevious: [{ region: "NA", revenue: 1.0 }],
    });
    expect(result).toEqual({
      model: "Holt-Winters",
      horizon: 6,
      projected: "$4.28M",
      ciLow: "$4.00M",
      ciHigh: "$4.56M",
      growth: "+12.0%",
      mape: "5.0%",
      series: [{ label: "m0", value: 3.0 }],
      topDrivers: [{ label: "NA revenue growth", pct: 100 }],
    });
  });
});
