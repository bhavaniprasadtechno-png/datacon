import { UnauthorizedException } from "@nestjs/common";
import type { ExecutionContext } from "@nestjs/common";
import { SupabaseAuthGuard } from "./supabase-auth.guard";
import * as supabaseAdminClient from "../supabase-admin.client";
import { PrismaService } from "../../prisma/prisma.service";

function contextWith(headers: Record<string, string>): ExecutionContext {
  return {
    switchToHttp: () => ({ getRequest: () => ({ headers }) }),
  } as unknown as ExecutionContext;
}

describe("SupabaseAuthGuard", () => {
  afterEach(() => jest.restoreAllMocks());

  it("throws Unauthorized when no bearer token is present", async () => {
    const guard = new SupabaseAuthGuard({} as PrismaService);
    await expect(guard.canActivate(contextWith({}))).rejects.toThrow(UnauthorizedException);
  });

  it("throws Unauthorized when getClaims rejects the token", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: { getClaims: jest.fn().mockResolvedValue({ data: null, error: new Error("bad token") }) },
    } as never);
    const guard = new SupabaseAuthGuard({} as PrismaService);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer bad" }))).rejects.toThrow(UnauthorizedException);
  });

  it("throws Unauthorized when no local profile row exists for the verified user", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: { getClaims: jest.fn().mockResolvedValue({ data: { claims: { sub: "ghost-id" } }, error: null }) },
    } as never);
    const prisma = { user: { findUnique: jest.fn().mockResolvedValue(null) } } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(UnauthorizedException);
  });

  it("attaches req.user with role permissions when the token and profile are valid", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest
          .fn()
          .mockResolvedValue({ data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, error: null }),
      },
    } as never);
    const prisma = {
      user: {
        findUnique: jest.fn().mockResolvedValue({
          id: "11111111-1111-1111-1111-111111111111",
          roleId: "admin",
          role: { permissions: [{ permissionKey: "manage_users" }] },
        }),
      },
    } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    const req: { headers: Record<string, string>; user?: unknown } = { headers: { authorization: "Bearer good" } };
    const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

    const result = await guard.canActivate(ctx);

    expect(result).toBe(true);
    expect(req.user).toEqual({
      id: "11111111-1111-1111-1111-111111111111",
      roleId: "admin",
      permissions: ["manage_users"],
    });
  });
});
