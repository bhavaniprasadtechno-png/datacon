import { BadRequestException, Injectable } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";
import { getSupabaseAdminClient } from "../auth/supabase-admin.client";
import { CreateOrganizationDto } from "./dto/create-organization.dto";
import { AccountStatus } from "@datacon/prisma";

const DEFAULT_PERMISSIONS_BY_ROLE: Record<string, string[]> = {
  viewer: ["view_dashboards", "ask_agents"],
  analyst: ["view_dashboards", "ask_agents", "export_data", "upload_docs", "manage_connectors"],
  admin: [
    "view_dashboards",
    "ask_agents",
    "export_data",
    "upload_docs",
    "manage_connectors",
    "manage_users",
    "manage_roles",
  ],
};

function initialsFor(name: string): string {
  const initials = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");
  return initials || "U";
}

@Injectable()
export class PlatformAdminService {
  // Uses `.scoped` throughout: PlatformAdminGuard + OrgContextInterceptor
  // together set `app.is_platform_admin`, which is what the RLS bypass on
  // organizations/users/roles/role_permissions checks.
  constructor(private readonly prisma: PrismaService) {}

  async listOrganizations() {
    return this.prisma.scoped.organization.findMany({
      orderBy: { createdAt: "asc" },
      include: { _count: { select: { users: true } } },
    });
  }

  async createOrganization(dto: CreateOrganizationDto) {
    const { data, error } = await getSupabaseAdminClient().auth.admin.inviteUserByEmail(dto.adminEmail, {
      data: { name: dto.adminName },
    });
    if (error || !data?.user) {
      throw new BadRequestException(error?.message ?? "Could not invite this organization's first admin.");
    }

    return this.prisma.scoped.$transaction(async (tx) => {
      const org = await tx.organization.create({ data: { name: dto.name } });

      let adminRoleId = "";
      for (const [roleId, permissions] of Object.entries(DEFAULT_PERMISSIONS_BY_ROLE)) {
        const role = await tx.role.create({
          data: {
            orgId: org.id,
            name: roleId.charAt(0).toUpperCase() + roleId.slice(1),
            isSystem: true,
            permissions: { create: permissions.map((key) => ({ permissionKey: key })) },
          },
        });
        if (roleId === "admin") adminRoleId = role.id;
      }

      await tx.user.create({
        data: {
          id: data.user.id,
          orgId: org.id,
          roleId: adminRoleId,
          name: dto.adminName,
          email: dto.adminEmail,
          initials: initialsFor(dto.adminName),
          isCore: false,
        },
      });

      return org;
    });
  }

  async listUsers(orgId: string) {
    return this.prisma.scoped.user.findMany({
      where: { orgId },
      select: {
        id: true,
        name: true,
        email: true,
        roleId: true,
        initials: true,
        avatarGrad: true,
        status: true,
        role: { select: { name: true } },
      },
      orderBy: { createdAt: "asc" },
    });
  }

  async setOrganizationStatus(orgId: string, status: AccountStatus) {
    return this.prisma.scoped.organization.update({ where: { id: orgId }, data: { status } });
  }

  async setUserStatus(userId: string, status: AccountStatus) {
    return this.prisma.scoped.user.update({ where: { id: userId }, data: { status } });
  }
}
