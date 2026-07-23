import { Controller, Get, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard as PermissionsAuthGuard } from "../auth/guards/permissions.guard";
import { RequireAnyPermission } from "../auth/decorators/require-any-permission.decorator";
import { PrismaService } from "../prisma/prisma.service";

@UseGuards(SupabaseAuthGuard, PermissionsAuthGuard)
@Controller("permissions")
export class PermissionsController {
  constructor(private readonly prisma: PrismaService) {}

  @RequireAnyPermission("manage_users", "manage_roles")
  @Get()
  list() {
    return this.prisma.permission.findMany({ orderBy: { key: "asc" } });
  }
}
