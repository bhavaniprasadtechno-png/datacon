import { Body, Controller, Delete, Get, Param, Patch, Post, Put, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { RequireAnyPermission } from "../auth/decorators/require-any-permission.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { RolesService } from "./roles.service";
import { CreateRoleDto } from "./dto/create-role.dto";
import { UpdateRoleDto } from "./dto/update-role.dto";
import { ApplyPermissionsMatrixDto } from "./dto/apply-permissions-matrix.dto";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("roles")
export class RolesController {
  constructor(private readonly roles: RolesService) {}

  // Needed by both the Assign-roles page (manage_users) and the Roles/Permissions pages (manage_roles).
  @RequireAnyPermission("manage_users", "manage_roles")
  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.roles.list(user.orgId);
  }

  @RequirePermissions("manage_roles")
  @Post()
  create(@CurrentUser() user: AuthenticatedUser, @Body() dto: CreateRoleDto) {
    return this.roles.create(user.orgId, dto);
  }

  @RequirePermissions("manage_roles")
  @Patch(":id")
  update(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string, @Body() dto: UpdateRoleDto) {
    return this.roles.update(user.orgId, id, dto);
  }

  @RequirePermissions("manage_roles")
  @Delete(":id")
  remove(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.roles.remove(user.orgId, id);
  }

  @RequirePermissions("manage_roles")
  @Put("permissions-matrix")
  applyMatrix(@CurrentUser() user: AuthenticatedUser, @Body() dto: ApplyPermissionsMatrixDto) {
    return this.roles.applyPermissionsMatrix(user.orgId, dto.matrix);
  }
}
