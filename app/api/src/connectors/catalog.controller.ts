import { Controller, Get, Param, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { ConnectorsService } from "./connectors.service";

@UseGuards(SupabaseAuthGuard)
@Controller("catalog")
export class CatalogController {
  constructor(private readonly connectors: ConnectorsService) {}

  @Get()
  list() {
    return this.connectors.catalog();
  }

  @Get(":id")
  preview(@Param("id") id: string) {
    return this.connectors.tablePreview(id);
  }
}
