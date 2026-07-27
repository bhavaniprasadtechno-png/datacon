import { CanActivate, ExecutionContext, ForbiddenException, Injectable, UnauthorizedException } from "@nestjs/common";
import { PrismaService } from "../../prisma/prisma.service";
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
    const userId = data?.claims?.sub as string | undefined;
    if (error || !userId) throw new UnauthorizedException("Invalid or expired token.");

    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      include: { role: { include: { permissions: true } }, org: { select: { status: true } } },
    });
    if (!user) throw new UnauthorizedException("No profile for this account.");
    if (user.status === "SUSPENDED" || user.org.status === "SUSPENDED") {
      throw new ForbiddenException("This account has been suspended.");
    }

    const authedUser: AuthenticatedUser = {
      id: user.id,
      orgId: user.orgId,
      roleId: user.roleId,
      permissions: user.role.permissions.map((p) => p.permissionKey),
    };
    req.user = authedUser;
    return true;
  }
}
