import { CanActivate, ExecutionContext, ForbiddenException, Injectable, UnauthorizedException } from "@nestjs/common";
import { PrismaService } from "../../prisma/prisma.service";
import { requestTxStorage } from "../../prisma/request-transaction.storage";
import { getSupabaseAdminClient } from "../supabase-admin.client";
import { AuthenticatedUser } from "../token.types";

function bearerToken(req: { headers?: Record<string, unknown> }): string | undefined {
  const header = req.headers?.["authorization"];
  return typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
}

@Injectable()
export class SupabaseAuthGuard implements CanActivate {
  constructor(private readonly prisma: PrismaService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest();
    const token = bearerToken(req);
    if (!token) throw new UnauthorizedException("Missing bearer token.");

    const { data, error } = await getSupabaseAdminClient().auth.getClaims(token);
    const claims = data?.claims;
    const userId = claims?.sub as string | undefined;
    if (error || !userId) throw new UnauthorizedException("Invalid or expired token.");

    const orgId = claims?.app_org_id as string | undefined;
    const roleId = claims?.app_role_id as string | undefined;
    const permissions = claims?.app_permissions as string[] | undefined;
    if (!orgId || !roleId || !permissions) {
      throw new UnauthorizedException("Session missing required claims — please sign in again.");
    }

    const reqTx = requestTxStorage.getStore();
    // const client = (reqTx?.tx ?? this.prisma) as unknown as Pick<PrismaService, "user">;
    // const status = await client.user.findUnique({
    //   where: { id: userId },
    //   select: { status: true, org: { select: { status: true } } },
    //   relationLoadStrategy: "join",
    // });
    // console.log(`[perf] guard: user.findUnique() done at +${performance.now() - t0}ms`); // TEMP
    // if (!status) throw new UnauthorizedException("No profile for this account.");
    // if (status.status === "SUSPENDED" || status.org.status === "SUSPENDED") {
    //   throw new ForbiddenException("This account has been suspended.");
    // }

    const authedUser: AuthenticatedUser = { id: userId, orgId, roleId, permissions };
    req.user = authedUser;
    return true;
  }
}
