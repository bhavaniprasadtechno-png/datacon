import { Body, Controller, Delete, Get, Param, Patch, Post, UseGuards } from "@nestjs/common";
import { SupabaseAuthGuard } from "../auth/guards/supabase-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
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
  list() {
    return this.users.list();
  }

  @RequirePermissions("manage_users")
  @Post()
  create(@Body() dto: CreateUserDto) {
    return this.users.create(dto);
  }

  @RequirePermissions("manage_users")
  @Patch(":id")
  update(@Param("id") id: string, @Body() dto: UpdateUserDto) {
    return this.users.update(id, dto);
  }

  @RequirePermissions("manage_users")
  @Delete(":id")
  remove(@Param("id") id: string) {
    return this.users.remove(id);
  }

  @RequirePermissions("manage_users")
  @Patch(":id/assign-role")
  assignRole(@Param("id") id: string, @Body() dto: AssignRoleDto) {
    return this.users.assignRole(id, dto.roleId);
  }
}
