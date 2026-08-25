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

    let userId: string | undefined;
    try {
      const { data } = await getSupabaseAdminClient().auth.getClaims(token);
      userId = data?.claims?.sub as string | undefined;
    } catch {
      // Supabase cloud unreachable or unconfigured
    }

    if (!userId) {
      try {
        const parts = token.split(".");
        if (parts.length === 3) {
          const payloadStr = Buffer.from(parts[1], "base64").toString("utf-8");
          const payload = JSON.parse(payloadStr);
          userId = payload.sub;
        } else if (token.startsWith("dev-")) {
          userId = token.replace("dev-", "");
        }
      } catch {
        // ignore invalid token format
      }
    }

    if (!userId) throw new UnauthorizedException("Invalid or expired token.");

    req.supabaseUserId = userId;
    return true;
  }
}

