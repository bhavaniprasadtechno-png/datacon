import { Controller, Get, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { InsightsService } from "./insights.service";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("insights")
export class InsightsController {
  constructor(private readonly insights: InsightsService) {}

  @RequirePermissions("view_dashboards")
  @Get()
  get() {
    return this.insights.get();
  }
}
