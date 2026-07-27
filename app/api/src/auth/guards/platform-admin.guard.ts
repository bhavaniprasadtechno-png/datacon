import { CanActivate, ExecutionContext, ForbiddenException, Injectable, UnauthorizedException } from "@nestjs/common";
import { PrismaService } from "../../prisma/prisma.service";
import { getSupabaseAdminClient } from "../supabase-admin.client";

function bearerToken(req: { headers?: Record<string, unknown> }): string | undefined {
  const header = req.headers?.["authorization"];
  return typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
}

@Injectable()
export class PlatformAdminGuard implements CanActivate {
  constructor(private readonly prisma: PrismaService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest();
    const token = bearerToken(req);
    if (!token) throw new UnauthorizedException("Missing bearer token.");

    const { data, error } = await getSupabaseAdminClient().auth.getClaims(token);
    const userId = data?.claims?.sub as string | undefined;
    if (error || !userId) throw new UnauthorizedException("Invalid or expired token.");

    const admin = await this.prisma.platformAdmin.findUnique({ where: { id: userId } });
    if (!admin) throw new ForbiddenException("Platform Admin access required.");

    req.platformAdmin = { id: admin.id, email: admin.email };
    return true;
  }
}
