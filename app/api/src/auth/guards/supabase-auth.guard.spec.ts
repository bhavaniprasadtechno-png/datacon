import { ForbiddenException, UnauthorizedException } from "@nestjs/common";
import type { ExecutionContext } from "@nestjs/common";
import { SupabaseAuthGuard } from "./supabase-auth.guard";
import * as supabaseAdminClient from "../supabase-admin.client";
import { PrismaService } from "../../prisma/prisma.service";
import { requestTxStorage } from "../../prisma/request-transaction.storage";

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
      auth: {
        getClaims: jest.fn().mockResolvedValue({
          data: {
            claims: { sub: "ghost-id", app_org_id: "acme-corp", app_role_id: "admin", app_permissions: [] },
          },
          error: null,
        }),
      },
    } as never);
    const prisma = { user: { findUnique: jest.fn().mockResolvedValue(null) } } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(UnauthorizedException);
  });

  it("attaches req.user built from the token's claims when RBAC claims and an active profile are present", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest.fn().mockResolvedValue({
          data: {
            claims: {
              sub: "11111111-1111-1111-1111-111111111111",
              app_org_id: "acme-corp",
              app_role_id: "admin",
              app_permissions: ["manage_users"],
            },
          },
          error: null,
        }),
      },
    } as never);
    const findUnique = jest.fn().mockResolvedValue({
      status: "ACTIVE",
      org: { status: "ACTIVE" },
    });
    const prisma = { user: { findUnique } } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    const req: { headers: Record<string, string>; user?: unknown } = { headers: { authorization: "Bearer good" } };
    const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

    const result = await guard.canActivate(ctx);

    expect(result).toBe(true);
    expect(req.user).toEqual({
      id: "11111111-1111-1111-1111-111111111111",
      orgId: "acme-corp",
      roleId: "admin",
      permissions: ["manage_users"],
    });
    expect(findUnique).toHaveBeenCalledWith({
      where: { id: "11111111-1111-1111-1111-111111111111" },
      select: { status: true, org: { select: { status: true } } },
      relationLoadStrategy: "join",
    });
  });

  it("throws Unauthorized when the token is missing the RBAC claims (pre-hook or stale token)", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest.fn().mockResolvedValue({
          data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } },
          error: null,
        }),
      },
    } as never);
    const guard = new SupabaseAuthGuard({} as PrismaService);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer stale" }))).rejects.toThrow(UnauthorizedException);
  });

  it("looks up the suspension status on the request-scoped transaction when one is open, instead of a separate query", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest.fn().mockResolvedValue({
          data: {
            claims: {
              sub: "11111111-1111-1111-1111-111111111111",
              app_org_id: "acme-corp",
              app_role_id: "admin",
              app_permissions: ["manage_users"],
            },
          },
          error: null,
        }),
      },
    } as never);
    const baseFindUnique = jest.fn();
    const txFindUnique = jest.fn().mockResolvedValue({ status: "ACTIVE", org: { status: "ACTIVE" } });
    const prisma = { user: { findUnique: baseFindUnique } } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    const req: { headers: Record<string, string>; user?: unknown } = { headers: { authorization: "Bearer good" } };
    const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

    const result = await requestTxStorage.run(
      { tx: { user: { findUnique: txFindUnique } } as never, rlsSet: false },
      () => guard.canActivate(ctx),
    );

    expect(result).toBe(true);
    expect(txFindUnique).toHaveBeenCalledTimes(1);
    expect(baseFindUnique).not.toHaveBeenCalled();
  });

  it("throws Forbidden when the user's own status is SUSPENDED", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest.fn().mockResolvedValue({
          data: {
            claims: {
              sub: "11111111-1111-1111-1111-111111111111",
              app_org_id: "acme-corp",
              app_role_id: "admin",
              app_permissions: [],
            },
          },
          error: null,
        }),
      },
    } as never);
    const prisma = {
      user: {
        findUnique: jest.fn().mockResolvedValue({
          status: "SUSPENDED",
          org: { status: "ACTIVE" },
        }),
      },
    } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(ForbiddenException);
  });

  it("throws Forbidden when the user's organization is SUSPENDED, even if the user themself is ACTIVE", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest.fn().mockResolvedValue({
          data: {
            claims: {
              sub: "11111111-1111-1111-1111-111111111111",
              app_org_id: "acme-corp",
              app_role_id: "admin",
              app_permissions: [],
            },
          },
          error: null,
        }),
      },
    } as never);
    const prisma = {
      user: {
        findUnique: jest.fn().mockResolvedValue({
          status: "ACTIVE",
          org: { status: "SUSPENDED" },
        }),
      },
    } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    await expect(guard.canActivate(contextWith({ authorization: "Bearer good" }))).rejects.toThrow(ForbiddenException);
  });
});
