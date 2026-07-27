import { Body, Controller, Delete, Get, Param, Post, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { ConnectorsService } from "./connectors.service";
import { SaveConnectorDto } from "./dto/save-connector.dto";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("connectors")
export class ConnectorsController {
  constructor(private readonly connectors: ConnectorsService) {}

  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.connectors.list(user.orgId);
  }

  @RequirePermissions("manage_connectors")
  @Post("test-draft")
  testDraft(@Body() dto: SaveConnectorDto) {
    return this.connectors.testDraft(dto);
  }

  @RequirePermissions("manage_connectors")
  @Post()
  create(@CurrentUser() user: AuthenticatedUser, @Body() dto: SaveConnectorDto) {
    return this.connectors.create(user.orgId, dto);
  }

  @RequirePermissions("manage_connectors")
  @Post(":id/sync")
  sync(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.connectors.syncNow(user.orgId, id);
  }

  @RequirePermissions("manage_connectors")
  @Delete(":id")
  remove(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.connectors.remove(user.orgId, id);
  }
}
