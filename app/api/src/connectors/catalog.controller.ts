import { Controller, Get, Param, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { ConnectorsService } from "./connectors.service";

@UseGuards(SupabaseAuthGuard)
@Controller("catalog")
export class CatalogController {
  constructor(private readonly connectors: ConnectorsService) {}

  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.connectors.catalog(user.orgId);
  }

  @Get(":id")
  preview(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.connectors.tablePreview(user.orgId, id);
  }
}
