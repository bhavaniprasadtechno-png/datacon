import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from "@nestjs/common";
import { getSupabaseAdminClient } from "../supabase-admin.client";

function bearerToken(req: { headers?: Record<string, unknown> }): string | undefined {
  const header = req.headers?.["authorization"];
  return typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
}

/** Verifies the bearer token only — no local-profile lookup. Used by routes
 * that must work for a Supabase-authenticated identity with no `users` or
 * `platform_admins` row yet (GET /auth/me, POST /auth/complete-registration). */
@Injectable()
export class SupabaseTokenGuard implements CanActivate {
  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest();
    const token = bearerToken(req);
    if (!token) throw new UnauthorizedException("Missing bearer token.");

    const { data, error } = await getSupabaseAdminClient().auth.getClaims(token);
    const userId = data?.claims?.sub as string | undefined;
    if (error || !userId) throw new UnauthorizedException("Invalid or expired token.");

    req.supabaseUserId = userId;
    return true;
  }
}
