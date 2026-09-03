import { Test } from "@nestjs/testing";
import { ConnectorsService } from "./connectors.service";
import { PrismaService } from "../prisma/prisma.service";
import { EncryptionService } from "../common/encryption.service";
import { AiClientService } from "../common/ai-client.service";

describe("ConnectorsService — sync result writes", () => {
  let service: ConnectorsService;
  let connector: { findUnique: jest.Mock; findUniqueOrThrow: jest.Mock; update: jest.Mock };
  let unifiedDataset: { deleteMany: jest.Mock; create: jest.Mock };
  let transactionFn: jest.Mock;
  let post: jest.Mock;

  beforeEach(async () => {
    connector = {
      findUnique: jest.fn().mockResolvedValue({ id: "c1", orgId: "org1", engine: "SQLITE", config: {}, secrets: {} }),
      findUniqueOrThrow: jest.fn().mockResolvedValue({ id: "c1", orgId: "org1", engine: "SQLITE", config: {}, secrets: {} }),
      update: jest.fn().mockResolvedValue({}),
    };
    unifiedDataset = { deleteMany: jest.fn().mockResolvedValue({}), create: jest.fn().mockResolvedValue({}) };
    transactionFn = jest.fn((cb: (tx: unknown) => unknown) => cb({}));
    post = jest.fn();

    const moduleRef = await Test.createTestingModule({
      providers: [
        ConnectorsService,
        {
          provide: PrismaService,
          useValue: { scoped: { connector, unifiedDataset }, $transaction: transactionFn },
        },
        { provide: EncryptionService, useValue: { decrypt: (s: string) => s } },
        { provide: AiClientService, useValue: { client: { post } } },
      ],
    }).compile();
    service = moduleRef.get(ConnectorsService);
  });

  it("writes the deleted+recreated datasets and the SYNCED status through a single transaction", async () => {
    post.mockResolvedValue({
      data: {
        ok: true,
        message: "synced",
        datasets: [
          { name: "leads", columns: ["id"], rowCount: 1, sampleRows: [["1"]] },
          { name: "notifications", columns: ["id"], rowCount: 1, sampleRows: [["1"]] },
        ],
      },
    });

    await service.syncNow("org1", "c1");

    expect(transactionFn).toHaveBeenCalledTimes(1);
    expect(unifiedDataset.deleteMany).toHaveBeenCalledWith({ where: { connectorId: "c1" } });
    expect(unifiedDataset.create).toHaveBeenCalledTimes(2);
    expect(connector.update).toHaveBeenCalledWith(expect.objectContaining({ data: expect.objectContaining({ status: "SYNCED" }) }));
  });

  it("marks the connector ERROR (outside the failed transaction) when a dataset write fails partway through", async () => {
    post.mockResolvedValue({
      data: {
        ok: true,
        message: "synced",
        datasets: [
          { name: "leads", columns: ["id"], rowCount: 1, sampleRows: [["1"]] },
          { name: "notifications", columns: ["id"], rowCount: 1, sampleRows: [["1"]] },
        ],
      },
    });
    unifiedDataset.create.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error("write failed"));

    await service.syncNow("org1", "c1");

    expect(connector.update).not.toHaveBeenCalledWith(expect.objectContaining({ data: expect.objectContaining({ status: "SYNCED" }) }));
    expect(connector.update).toHaveBeenCalledWith(expect.objectContaining({ data: expect.objectContaining({ status: "ERROR" }) }));
  });
});
