import { Body, Controller, Get, Param, Patch, Post, UseGuards } from "@nestjs/common";
import { PlatformAdminGuard } from "../auth/guards/platform-admin.guard";
import { PlatformAdminService } from "./platform-admin.service";
import { CreateOrganizationDto } from "./dto/create-organization.dto";
import { UpdateStatusDto } from "./dto/update-status.dto";

@UseGuards(PlatformAdminGuard)
@Controller("platform-admin/organizations")
export class PlatformAdminController {
  constructor(private readonly platformAdmin: PlatformAdminService) {}

  @Get()
  list() {
    return this.platformAdmin.listOrganizations();
  }

  @Post()
  create(@Body() dto: CreateOrganizationDto) {
    return this.platformAdmin.createOrganization(dto);
  }

  @Patch(":orgId/status")
  setOrganizationStatus(@Param("orgId") orgId: string, @Body() dto: UpdateStatusDto) {
    return this.platformAdmin.setOrganizationStatus(orgId, dto.status);
  }

  @Get(":orgId/users")
  listUsers(@Param("orgId") orgId: string) {
    return this.platformAdmin.listUsers(orgId);
  }

  @Patch(":orgId/users/:userId/status")
  setUserStatus(@Param("userId") userId: string, @Body() dto: UpdateStatusDto) {
    return this.platformAdmin.setUserStatus(userId, dto.status);
  }
}
