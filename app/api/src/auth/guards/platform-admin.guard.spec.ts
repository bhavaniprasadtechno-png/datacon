import { ForbiddenException, UnauthorizedException } from "@nestjs/common";
import type { ExecutionContext } from "@nestjs/common";
import { PlatformAdminGuard } from "./platform-admin.guard";
import * as supabaseAdminClient from "../supabase-admin.client";
import { PrismaService } from "../../prisma/prisma.service";

function contextWith(headers: Record<string, string>): ExecutionContext {
  const req: { headers: Record<string, string>; platformAdmin?: unknown } = { headers };
  return { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;
}

describe("PlatformAdminGuard", () => {
  afterEach(() => jest.restoreAllMocks());

  it("throws Unauthorized when no bearer token is present", async () => {
    const guard = new PlatformAdminGuard({} as PrismaService);
    await expect(guard.canActivate(contextWith({}))).rejects.toThrow(UnauthorizedException);
  });

  it("throws Forbidden when the verified user has no PlatformAdmin row", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest
          .fn()
          .mockResolvedValue({ data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, error: null }),
      },
    } as never);
    const prisma = { platformAdmin: { findUnique: jest.fn().mockResolvedValue(null) } } as unknown as PrismaService;
    const guard = new PlatformAdminGuard(prisma);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(ForbiddenException);
  });

  it("attaches req.platformAdmin when a PlatformAdmin row exists", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest
          .fn()
          .mockResolvedValue({ data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, error: null }),
      },
    } as never);
    const prisma = {
      platformAdmin: {
        findUnique: jest.fn().mockResolvedValue({ id: "11111111-1111-1111-1111-111111111111", email: "pa@datacon.internal" }),
      },
    } as unknown as PrismaService;
    const guard = new PlatformAdminGuard(prisma);
    const req: { headers: Record<string, string>; platformAdmin?: unknown } = { headers: { authorization: "Bearer good" } };
    const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

    const result = await guard.canActivate(ctx);

    expect(result).toBe(true);
    expect(req.platformAdmin).toEqual({ id: "11111111-1111-1111-1111-111111111111", email: "pa@datacon.internal" });
  });
});
