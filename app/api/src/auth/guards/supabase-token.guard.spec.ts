import { UnauthorizedException } from "@nestjs/common";
import type { ExecutionContext } from "@nestjs/common";
import { SupabaseTokenGuard } from "./supabase-token.guard";
import * as supabaseAdminClient from "../supabase-admin.client";

function contextWith(headers: Record<string, string>, req: Record<string, unknown> = {}): ExecutionContext {
  const reqObj = { headers, ...req };
  return { switchToHttp: () => ({ getRequest: () => reqObj }) } as unknown as ExecutionContext;
}

describe("SupabaseTokenGuard", () => {
  afterEach(() => jest.restoreAllMocks());

  it("throws Unauthorized when no bearer token is present", async () => {
    const guard = new SupabaseTokenGuard();
    await expect(guard.canActivate(contextWith({}))).rejects.toThrow(UnauthorizedException);
  });

  it("throws Unauthorized when getClaims rejects the token", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: { getClaims: jest.fn().mockResolvedValue({ data: null, error: new Error("bad token") }) },
    } as never);
    const guard = new SupabaseTokenGuard();
    await expect(guard.canActivate(contextWith({ authorization: "Bearer bad" }))).rejects.toThrow(UnauthorizedException);
  });

  it("attaches req.supabaseUserId when the token is valid", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest
          .fn()
          .mockResolvedValue({ data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, error: null }),
      },
    } as never);
    const guard = new SupabaseTokenGuard();
    const req: { headers: Record<string, string>; supabaseUserId?: string } = { headers: { authorization: "Bearer good" } };
    const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

    const result = await guard.canActivate(ctx);

    expect(result).toBe(true);
    expect(req.supabaseUserId).toBe("11111111-1111-1111-1111-111111111111");
  });
});
