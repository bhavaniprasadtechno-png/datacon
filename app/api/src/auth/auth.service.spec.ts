import { ForbiddenException } from "@nestjs/common";
import { Test } from "@nestjs/testing";
import { AuthService } from "./auth.service";
import { PrismaService } from "../prisma/prisma.service";

describe("AuthService.completeRegistration", () => {
  it("is idempotent — returns the existing profile if one already exists", async () => {
    const prisma = {
      scoped: {
        user: {
          findUnique: jest.fn().mockResolvedValue({ id: "u1", orgId: "org1" }),
        },
      },
    } as unknown as PrismaService;
    const module = await Test.createTestingModule({
      providers: [AuthService, { provide: PrismaService, useValue: prisma }],
    }).compile();
    const service = module.get(AuthService);

    const result = await service.completeRegistration("u1", "Jordan Lee", "Jordan's Workspace");

    expect(result).toEqual({ id: "u1", orgId: "org1" });
    expect((prisma as any).scoped.user.findUnique).toHaveBeenCalledWith({ where: { id: "u1" } });
  });
});

describe("AuthService.me", () => {
  function servicWith(userRow: Record<string, unknown>) {
    const prisma = {
      scoped: {
        platformAdmin: { findUnique: jest.fn().mockResolvedValue(null) },
        user: { findUniqueOrThrow: jest.fn().mockResolvedValue(userRow) },
      },
    } as unknown as PrismaService;
    return { prisma };
  }

  it("throws Forbidden when the user's own status is SUSPENDED", async () => {
    const { prisma } = servicWith({
      id: "u1",
      orgId: "org1",
      status: "SUSPENDED",
      org: { status: "ACTIVE" },
      role: { name: "Admin", permissions: [] },
    });
    const module = await Test.createTestingModule({
      providers: [AuthService, { provide: PrismaService, useValue: prisma }],
    }).compile();
    const service = module.get(AuthService);

    await expect(service.me("u1")).rejects.toThrow(ForbiddenException);
  });

  it("throws Forbidden when the user's organization is SUSPENDED, even if the user themself is ACTIVE", async () => {
    const { prisma } = servicWith({
      id: "u1",
      orgId: "org1",
      status: "ACTIVE",
      org: { status: "SUSPENDED" },
      role: { name: "Admin", permissions: [] },
    });
    const module = await Test.createTestingModule({
      providers: [AuthService, { provide: PrismaService, useValue: prisma }],
    }).compile();
    const service = module.get(AuthService);

    await expect(service.me("u1")).rejects.toThrow(ForbiddenException);
  });

  it("returns the org-member profile for an ACTIVE user in an ACTIVE org", async () => {
    const { prisma } = servicWith({
      id: "u1",
      orgId: "org1",
      name: "Jordan Lee",
      email: "jordan@acme.com",
      initials: "JL",
      avatarGrad: "var(--ac-grad)",
      title: null,
      roleId: "admin",
      status: "ACTIVE",
      org: { status: "ACTIVE" },
      role: { name: "Admin", permissions: [] },
    });
    const module = await Test.createTestingModule({
      providers: [AuthService, { provide: PrismaService, useValue: prisma }],
    }).compile();
    const service = module.get(AuthService);

    const result = await service.me("u1");

    expect(result).toMatchObject({ kind: "org_member", id: "u1", roleName: "Admin" });
  });
});
