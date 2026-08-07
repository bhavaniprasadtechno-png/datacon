import { BadRequestException, Injectable, NotFoundException } from "@nestjs/common";
import { Intent } from "@datacon/prisma";
import { PrismaService } from "../prisma/prisma.service";
import { SaveDashletDto } from "./dto/save-dashlet.dto";

const INTENT_MAP: Record<string, Intent> = {
  descriptive: "DESCRIPTIVE",
  diagnostic: "DIAGNOSTIC",
  predictive: "PREDICTIVE",
  prescriptive: "PRESCRIPTIVE",
};

@Injectable()
export class DashboardsService {
  constructor(private readonly prisma: PrismaService) {}

  async list(orgId: string, userId: string) {
    const rows = await this.prisma.scoped.dashboard.findMany({
      where: { orgId, userId },
      include: { _count: { select: { dashlets: true } } },
      orderBy: { createdAt: "desc" },
    });
    return rows.map((r: any) => ({ id: r.id, name: r.name, dashletCount: r._count.dashlets, updatedAt: r.updatedAt }));
  }

  async save(orgId: string, userId: string, dto: SaveDashletDto) {
    let dashboardId: string;
    if (dto.dashboardId) {
      const owned = await this.assertOwnedDashboard(orgId, userId, dto.dashboardId);
      dashboardId = owned.id;
    } else {
      if (!dto.name?.trim()) throw new BadRequestException("Dashboard name is required.");
      const created = await this.prisma.scoped.dashboard.create({ data: { orgId, userId, name: dto.name.trim() } });
      dashboardId = created.id;
    }

    await this.prisma.scoped.dashlet.create({
      data: {
        orgId,
        dashboardId,
        title: dto.title,
        text: dto.text,
        intent: INTENT_MAP[dto.intent],
        payload: dto.payload as any,
      },
    });

    return this.detail(orgId, userId, dashboardId);
  }

  private async assertOwnedDashboard(orgId: string, userId: string, id: string) {
    const row = await this.prisma.scoped.dashboard.findUnique({ where: { id } });
    if (!row || row.orgId !== orgId || row.userId !== userId) throw new NotFoundException("Dashboard not found.");
    return row;
  }

  async detail(orgId: string, userId: string, id: string) {
    await this.assertOwnedDashboard(orgId, userId, id);
    const dashboard = await this.prisma.scoped.dashboard.findUniqueOrThrow({
      where: { id },
      include: { dashlets: { orderBy: { createdAt: "asc" } } },
    });

    const dashlets = dashboard.dashlets.map((d: any) => ({
      id: d.id,
      title: d.title,
      text: d.text,
      intent: (d.intent as string).toLowerCase(),
      payload: d.payload,
    }));

    return { id: dashboard.id, name: dashboard.name, dashlets };
  }

  async removeDashlet(orgId: string, userId: string, dashboardId: string, dashletId: string) {
    await this.assertOwnedDashboard(orgId, userId, dashboardId);
    await this.prisma.scoped.dashlet.delete({ where: { id: dashletId } });
    return { ok: true };
  }
}
