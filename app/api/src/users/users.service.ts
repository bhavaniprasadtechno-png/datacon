import { BadRequestException, ConflictException, ForbiddenException, Injectable, NotFoundException } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";
import { getSupabaseAdminClient } from "../auth/supabase-admin.client";
import { CreateUserDto } from "./dto/create-user.dto";
import { UpdateUserDto } from "./dto/update-user.dto";

const AVATAR_GRADIENTS = [
  "var(--ac-grad)",
  "linear-gradient(135deg,#ff8a5c,#ff5c7a)",
  "linear-gradient(135deg,#1fb6a6,#13a06b)",
  "linear-gradient(135deg,#5b8def,#3f6fd6)",
  "linear-gradient(135deg,#f2a65a,#e2603f)",
];

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
export class UsersService {
  constructor(private readonly prisma: PrismaService) {}

  private select() {
    return {
      id: true,
      name: true,
      email: true,
      initials: true,
      avatarGrad: true,
      title: true,
      isCore: true,
      createdAt: true,
      roleId: true,
      role: { select: { id: true, name: true, colorHex: true, bgHex: true, permissions: { select: { permissionKey: true } } } },
    } as const;
  }

  async list(orgId: string) {
    const users = await this.prisma.scoped.user.findMany({ where: { orgId }, select: this.select(), orderBy: { createdAt: "asc" } });
    return users.map((u) => ({ ...u, canDelete: !u.isCore, permissionCount: u.role.permissions.length }));
  }

  async create(orgId: string, dto: CreateUserDto) {
    const existing = await this.prisma.scoped.user.findUnique({ where: { email: dto.email } });
    if (existing) throw new ConflictException("An account with this email already exists.");
    const role = await this.prisma.scoped.role.findUnique({ where: { id: dto.roleId } });
    if (!role || role.orgId !== orgId) throw new BadRequestException("Unknown role.");

    const { data, error } = await getSupabaseAdminClient().auth.admin.inviteUserByEmail(dto.email, {
      data: { name: dto.name },
    });
    if (error || !data?.user) {
      throw new BadRequestException(error?.message ?? "Could not invite this user.");
    }

    const count = await this.prisma.scoped.user.count({ where: { orgId } });
    const user = await this.prisma.scoped.user.upsert({
      where: { id: data.user.id },
      update: { name: dto.name, title: dto.title, roleId: dto.roleId },
      create: {
        id: data.user.id,
        orgId,
        name: dto.name,
        email: dto.email,
        title: dto.title,
        roleId: dto.roleId,
        initials: initialsFor(dto.name),
        avatarGrad: AVATAR_GRADIENTS[count % AVATAR_GRADIENTS.length],
        isCore: false,
      },
      select: this.select(),
    });
    return { ...user, canDelete: true, permissionCount: user.role.permissions.length };
  }

  async update(orgId: string, id: string, dto: UpdateUserDto) {
    const user = await this.prisma.scoped.user.findUnique({ where: { id } });
    if (!user || user.orgId !== orgId) throw new NotFoundException("User not found.");
    if (dto.roleId) {
      const role = await this.prisma.scoped.role.findUnique({ where: { id: dto.roleId } });
      if (!role || role.orgId !== orgId) throw new BadRequestException("Unknown role.");
    }
    const updated = await this.prisma.scoped.user.update({
      where: { id },
      data: { name: dto.name, email: dto.email, roleId: dto.roleId },
      select: this.select(),
    });
    return { ...updated, canDelete: !updated.isCore, permissionCount: updated.role.permissions.length };
  }

  async remove(orgId: string, id: string) {
    const user = await this.prisma.scoped.user.findUnique({ where: { id } });
    if (!user || user.orgId !== orgId) throw new NotFoundException("User not found.");
    if (user.isCore) throw new ForbiddenException("This is a core demo account and can't be removed.");
    await this.prisma.scoped.user.delete({ where: { id } });
    return { ok: true };
  }

  async assignRole(orgId: string, id: string, roleId: string) {
    const role = await this.prisma.scoped.role.findUnique({ where: { id: roleId } });
    if (!role || role.orgId !== orgId) throw new BadRequestException("Unknown role.");
    const updated = await this.prisma.scoped.user.update({
      where: { id },
      data: { roleId },
      select: this.select(),
    });
    return { ...updated, canDelete: !updated.isCore, permissionCount: updated.role.permissions.length };
  }
}
