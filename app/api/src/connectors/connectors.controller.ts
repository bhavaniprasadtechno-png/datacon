import { Body, Controller, Delete, Get, Param, Post, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { ConnectorsService } from "./connectors.service";
import { SaveConnectorDto } from "./dto/save-connector.dto";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("connectors")
export class ConnectorsController {
  constructor(private readonly connectors: ConnectorsService) {}

  @Get()
  list() {
    return this.connectors.list();
  }

  @RequirePermissions("manage_connectors")
  @Post("test-draft")
  testDraft(@Body() dto: SaveConnectorDto) {
    return this.connectors.testDraft(dto);
  }

  @RequirePermissions("manage_connectors")
  @Post()
  create(@Body() dto: SaveConnectorDto) {
    return this.connectors.create(dto);
  }

  @RequirePermissions("manage_connectors")
  @Post(":id/sync")
  sync(@Param("id") id: string) {
    return this.connectors.syncNow(id);
  }

  @RequirePermissions("manage_connectors")
  @Delete(":id")
  remove(@Param("id") id: string) {
    return this.connectors.remove(id);
  }
}
