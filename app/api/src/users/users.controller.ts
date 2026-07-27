import { Body, Controller, Delete, Get, Param, Patch, Post, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { UsersService } from "./users.service";
import { CreateUserDto } from "./dto/create-user.dto";
import { UpdateUserDto } from "./dto/update-user.dto";
import { AssignRoleDto } from "./dto/assign-role.dto";

@UseGuards(SupabaseAuthGuard, PermissionsGuard)
@Controller("users")
export class UsersController {
  constructor(private readonly users: UsersService) {}

  @RequirePermissions("manage_users")
  @Get()
  list(@CurrentUser() user: AuthenticatedUser) {
    return this.users.list(user.orgId);
  }

  @RequirePermissions("manage_users")
  @Post()
  create(@CurrentUser() user: AuthenticatedUser, @Body() dto: CreateUserDto) {
    return this.users.create(user.orgId, dto);
  }

  @RequirePermissions("manage_users")
  @Patch(":id")
  update(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string, @Body() dto: UpdateUserDto) {
    return this.users.update(user.orgId, id, dto);
  }

  @RequirePermissions("manage_users")
  @Delete(":id")
  remove(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string) {
    return this.users.remove(user.orgId, id);
  }

  @RequirePermissions("manage_users")
  @Patch(":id/assign-role")
  assignRole(@CurrentUser() user: AuthenticatedUser, @Param("id") id: string, @Body() dto: AssignRoleDto) {
    return this.users.assignRole(user.orgId, id, dto.roleId);
  }
}
