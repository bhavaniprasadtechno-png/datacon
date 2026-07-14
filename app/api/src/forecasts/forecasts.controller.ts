import { Controller, Get, Query, UseGuards } from "@nestjs/common";
import { JwtAuthGuard } from "../auth/guards/jwt-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { MetricsService } from "../metrics/metrics.service";
import { AiClientService } from "../common/ai-client.service";

const VALID_MODELS = new Set(["OLS", "Holt-Winters"]);
const VALID_HORIZONS = new Set([3, 6, 12]);

@UseGuards(JwtAuthGuard, PermissionsGuard)
@Controller("forecasts")
export class ForecastsController {
  constructor(
    private readonly metrics: MetricsService,
    private readonly ai: AiClientService,
  ) {}

  @RequirePermissions("view_dashboards")
  @Get()
  async get(@Query("model") modelQuery?: string, @Query("horizon") horizonQuery?: string) {
    const model = VALID_MODELS.has(modelQuery ?? "") ? (modelQuery as string) : "Holt-Winters";
    const horizon = VALID_HORIZONS.has(Number(horizonQuery)) ? Number(horizonQuery) : 6;

    const [series, regionRevenue] = await Promise.all([this.metrics.revenueHistory(), this.metrics.regionRevenue()]);

    if (series.length < 2) {
      return {
        model,
        horizon,
        projected: "No data",
        ciLow: "No data",
        ciHigh: "No data",
        growth: "No data",
        mape: "No data",
        series: [],
        topDrivers: [],
      };
    }

    const res = await this.ai.client.post("/internal/forecast", {
      series,
      model,
      horizonMonths: horizon,
      regionRevenueCurrent: regionRevenue.current,
      regionRevenuePrevious: regionRevenue.previous,
    });

    return { model, horizon, ...res.data };
  }
}
