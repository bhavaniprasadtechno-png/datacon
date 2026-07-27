import { ForbiddenException, Injectable } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";

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
  const initials = name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  return initials || "U";
}

@Injectable()
export class AuthService {
  constructor(private readonly prisma: PrismaService) {}

  private async userWithPermissions(userId: string) {
    // .scoped, not plain — see the class-level note below on why every
    // method here needs the is_platform_admin RLS bypass.
    const user = await this.prisma.scoped.user.findUniqueOrThrow({
      where: { id: userId },
      include: { role: { include: { permissions: true } }, org: { select: { status: true } } },
    });
    if (user.status === "SUSPENDED" || user.org.status === "SUSPENDED") {
      throw new ForbiddenException("This account has been suspended.");
    }
    return { user, permissions: user.role.permissions.map((p) => p.permissionKey) };
  }

  /** GET /auth/me and POST /auth/complete-registration both run with
   * `@Bootstrapping()` on their controller routes (OrgContextInterceptor
   * sets `app.is_platform_admin` for those routes), which is what lets
   * these two methods' `.scoped` queries see the calling user's own row
   * before any `app.current_org_id` is known — the same RLS bypass a real
   * Platform Admin gets on users/roles/role_permissions/organizations,
   * just scoped in practice by every query below being hardcoded to the
   * caller's own verified supabaseUserId, never a listing. Plain
   * (non-`.scoped`) `this.prisma` calls would silently return zero rows
   * here, since no session var would ever be set for them. */

  /** GET /auth/me — checks PlatformAdmin first (disjoint identity space from
   * `users`), then falls back to the org-member profile. */
  async me(supabaseUserId: string) {
    const platformAdmin = await this.prisma.scoped.platformAdmin.findUnique({ where: { id: supabaseUserId } });
    if (platformAdmin) {
      return { kind: "platform_admin" as const, id: platformAdmin.id, email: platformAdmin.email };
    }

    const { user, permissions } = await this.userWithPermissions(supabaseUserId);
    return {
      kind: "org_member" as const,
      id: user.id,
      orgId: user.orgId,
      name: user.name,
      email: user.email,
      initials: user.initials,
      avatarGrad: user.avatarGrad,
      title: user.title,
      roleId: user.roleId,
      roleName: user.role.name,
      permissions,
    };
  }

  /** POST /auth/complete-registration — the self-registration bootstrap: a
   * brand-new Organization, its 3 default Roles + permissions, and the
   * calling Supabase user as that org's Admin. Idempotent on supabaseUserId
   * so a retry after a partial failure is safe. */
  async completeRegistration(supabaseUserId: string, name: string, orgName: string) {
    const existing = await this.prisma.scoped.user.findUnique({ where: { id: supabaseUserId } });
    if (existing) return existing;

    return this.prisma.scoped.$transaction(async (tx) => {
      const org = await tx.organization.create({ data: { name: orgName } });

      const roles: Record<string, { id: string }> = {};
      for (const [roleId, permissions] of Object.entries(DEFAULT_PERMISSIONS_BY_ROLE)) {
        const role = await tx.role.create({
          data: {
            orgId: org.id,
            name: roleId.charAt(0).toUpperCase() + roleId.slice(1),
            isSystem: true,
            permissions: { create: permissions.map((key) => ({ permissionKey: key })) },
          },
        });
        roles[roleId] = role;
      }

      return tx.user.create({
        data: {
          id: supabaseUserId,
          orgId: org.id,
          roleId: roles.admin.id,
          name,
          email: (await tx.$queryRaw<{ email: string }[]>`SELECT email FROM auth.users WHERE id = ${supabaseUserId}::uuid`)[0]?.email ?? "",
          initials: initialsFor(name),
          isCore: false,
        },
      });
    });
  }
}
