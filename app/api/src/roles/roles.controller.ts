import { Body, Controller, Delete, Get, Param, Patch, Post, Put, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { RequireAnyPermission } from "../auth/decorators/require-any-permission.decorator";
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
  list() {
    return this.roles.list();
  }

  @RequirePermissions("manage_roles")
  @Post()
  create(@Body() dto: CreateRoleDto) {
    return this.roles.create(dto);
  }

  @RequirePermissions("manage_roles")
  @Patch(":id")
  update(@Param("id") id: string, @Body() dto: UpdateRoleDto) {
    return this.roles.update(id, dto);
  }

  @RequirePermissions("manage_roles")
  @Delete(":id")
  remove(@Param("id") id: string) {
    return this.roles.remove(id);
  }

  @RequirePermissions("manage_roles")
  @Put("permissions-matrix")
  applyMatrix(@Body() dto: ApplyPermissionsMatrixDto) {
    return this.roles.applyPermissionsMatrix(dto.matrix);
  }
}
