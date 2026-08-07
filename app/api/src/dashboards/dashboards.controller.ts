import { Body, Controller, Delete, Get, Param, Post, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { DashboardsService } from "./dashboards.service";
import { SaveDashletDto } from "./dto/save-dashlet.dto";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@RequirePermissions("view_dashboards")
@Controller("dashboards")
export class DashboardsController {
  constructor(private readonly dashboards: DashboardsService) {}

  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.dashboards.list(user.orgId, user.id);
  }

  @Post("save")
  save(@CurrentUser() user: AuthenticatedUser, @Body() dto: SaveDashletDto) {
    return this.dashboards.save(user.orgId, user.id, dto);
  }

  @Get(":id")
  detail(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.dashboards.detail(user.orgId, user.id, id);
  }

  @Delete(":id/dashlets/:dashletId")
  removeDashlet(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string, @Param("dashletId") dashletId: string) {
    return this.dashboards.removeDashlet(user.orgId, user.id, id, dashletId);
  }
}
