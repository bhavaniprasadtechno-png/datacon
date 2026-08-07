import { BadRequestException, NotFoundException } from "@nestjs/common";
import { Test } from "@nestjs/testing";
import { DashboardsService } from "./dashboards.service";
import { PrismaService } from "../prisma/prisma.service";

describe("DashboardsService", () => {
  let service: DashboardsService;
  let dashboard: { findMany: jest.Mock; findUnique: jest.Mock; findUniqueOrThrow: jest.Mock; create: jest.Mock };
  let dashlet: { create: jest.Mock; delete: jest.Mock };

  beforeEach(async () => {
    dashboard = { findMany: jest.fn(), findUnique: jest.fn(), findUniqueOrThrow: jest.fn(), create: jest.fn() };
    dashlet = { create: jest.fn(), delete: jest.fn() };
    const moduleRef = await Test.createTestingModule({
      providers: [DashboardsService, { provide: PrismaService, useValue: { scoped: { dashboard, dashlet } } }],
    }).compile();
    service = moduleRef.get(DashboardsService);
  });

  it("creates a new dashboard when dashboardId is omitted", async () => {
    dashboard.create.mockResolvedValue({ id: "d1" });
    dashlet.create.mockResolvedValue({ id: "dl1" });
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "user1" });
    dashboard.findUniqueOrThrow.mockResolvedValue({ id: "d1", name: "Revenue Watch", dashlets: [] });

    const result = await service.save("org1", "user1", {
      name: "Revenue Watch",
      title: "Revenue by region",
      text: "Here is what I found.",
      intent: "descriptive",
      payload: { chart: { type: "bar", title: "t", data: [] } },
    } as any);

    expect(dashboard.create).toHaveBeenCalledWith({ data: { orgId: "org1", userId: "user1", name: "Revenue Watch" } });
    expect(dashlet.create).toHaveBeenCalledWith({
      data: {
        orgId: "org1",
        dashboardId: "d1",
        title: "Revenue by region",
        text: "Here is what I found.",
        intent: "DESCRIPTIVE",
        payload: { chart: { type: "bar", title: "t", data: [] } },
      },
    });
    expect(result.id).toBe("d1");
  });

  it("rejects a new-dashboard save with no name", async () => {
    await expect(
      service.save("org1", "user1", { title: "t", text: "t", intent: "descriptive", payload: {} } as any),
    ).rejects.toThrow(BadRequestException);
    expect(dashboard.create).not.toHaveBeenCalled();
  });

  it("appends to an existing dashboard owned by the requesting user", async () => {
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "user1" });
    dashlet.create.mockResolvedValue({ id: "dl1" });
    dashboard.findUniqueOrThrow.mockResolvedValue({ id: "d1", name: "Revenue Watch", dashlets: [] });

    await service.save("org1", "user1", {
      dashboardId: "d1",
      title: "t",
      text: "t",
      intent: "predictive",
      payload: {},
    } as any);

    expect(dashboard.create).not.toHaveBeenCalled();
    expect(dashlet.create).toHaveBeenCalledWith({ data: expect.objectContaining({ dashboardId: "d1", intent: "PREDICTIVE" }) });
  });

  it("rejects appending to a dashboard owned by a different user", async () => {
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "someone-else" });

    await expect(
      service.save("org1", "user1", { dashboardId: "d1", title: "t", text: "t", intent: "descriptive", payload: {} } as any),
    ).rejects.toThrow(NotFoundException);
    expect(dashlet.create).not.toHaveBeenCalled();
  });

  it("returns each dashlet's stored payload directly, no AI involvement", async () => {
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "user1" });
    dashboard.findUniqueOrThrow.mockResolvedValue({
      id: "d1",
      name: "Revenue Watch",
      dashlets: [{ id: "dl1", title: "Revenue by region", text: "t", intent: "DESCRIPTIVE", payload: { confidence: "high", table: { columns: ["a"], rows: [[1]] } } }],
    });

    const result = await service.detail("org1", "user1", "d1");

    expect(result.dashlets[0]).toEqual({
      id: "dl1",
      title: "Revenue by region",
      text: "t",
      intent: "descriptive",
      payload: { confidence: "high", table: { columns: ["a"], rows: [[1]] } },
    });
  });

  it("rejects detail/removeDashlet for a dashboard not owned by the requesting user", async () => {
    dashboard.findUnique.mockResolvedValue(null);
    await expect(service.detail("org1", "user1", "missing")).rejects.toThrow(NotFoundException);
    await expect(service.removeDashlet("org1", "user1", "missing", "dl1")).rejects.toThrow(NotFoundException);
    expect(dashlet.delete).not.toHaveBeenCalled();
  });

  it("removes a dashlet from an owned dashboard", async () => {
    dashboard.findUnique.mockResolvedValue({ id: "d1", orgId: "org1", userId: "user1" });
    dashlet.delete.mockResolvedValue({ id: "dl1" });

    const result = await service.removeDashlet("org1", "user1", "d1", "dl1");

    expect(dashlet.delete).toHaveBeenCalledWith({ where: { id: "dl1" } });
    expect(result).toEqual({ ok: true });
  });
});
