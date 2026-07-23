import { Injectable } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";

@Injectable()
export class AuthService {
  constructor(private readonly prisma: PrismaService) {}

  private async userWithPermissions(userId: string) {
    const user = await this.prisma.user.findUniqueOrThrow({
      where: { id: userId },
      include: { role: { include: { permissions: true } } },
    });
    return {
      user,
      permissions: user.role.permissions.map((p) => p.permissionKey),
    };
  }

  /** Public quick-login roster shown on the login screen (demo personas only). */
  async personas() {
    const users = await this.prisma.user.findMany({
      where: { isCore: true },
      select: {
        id: true,
        name: true,
        email: true,
        title: true,
        initials: true,
        avatarGrad: true,
        roleId: true,
        role: { select: { name: true, colorHex: true, bgHex: true } },
      },
      orderBy: { createdAt: "asc" },
    });
    return users;
  }

  async me(userId: string) {
    const { user, permissions } = await this.userWithPermissions(userId);
    return {
      id: user.id,
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
}
