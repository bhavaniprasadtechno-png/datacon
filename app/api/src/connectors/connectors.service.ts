import { BadRequestException, Injectable, NotFoundException } from "@nestjs/common";
import { ConnectorEngine } from "@datacon/prisma";
import { allFields, secretFieldKeys, type ConnectorEngineId } from "@datacon/shared-types";
import { PrismaService } from "../prisma/prisma.service";
import { EncryptionService } from "../common/encryption.service";
import { AiClientService } from "../common/ai-client.service";
import { SaveConnectorDto } from "./dto/save-connector.dto";

const MASK = "••••••••";

function toEngineEnum(id: ConnectorEngineId): ConnectorEngine {
  return id.toUpperCase() as ConnectorEngine;
}

function toEngineId(engine: ConnectorEngine): ConnectorEngineId {
  return engine.toLowerCase() as ConnectorEngineId;
}

@Injectable()
export class ConnectorsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly encryption: EncryptionService,
    private readonly ai: AiClientService,
  ) {}

  private validateFields(engineId: ConnectorEngineId, fields: Record<string, string>) {
    const defs = allFields(engineId);
    for (const f of defs) {
      if (f.required && !fields[f.key]?.trim()) {
        throw new BadRequestException(`${f.label} is required.`);
      }
    }
  }

  private splitFields(engineId: ConnectorEngineId, fields: Record<string, string>) {
    const secretKeys = new Set(secretFieldKeys(engineId));
    const config: Record<string, string> = {};
    const plainSecrets: Record<string, string> = {};
    for (const [key, value] of Object.entries(fields)) {
      if (value === undefined || value === null) continue;
      if (secretKeys.has(key)) plainSecrets[key] = value;
      else config[key] = value;
    }
    return { config, plainSecrets, secretKeys };
  }

  private encryptSecrets(plainSecrets: Record<string, string>): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(plainSecrets)) {
      if (value) out[key] = this.encryption.encrypt(value);
    }
    return out;
  }

  private decryptSecrets(encrypted: Record<string, string>): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(encrypted ?? {})) {
      out[key] = this.encryption.decrypt(value);
    }
    return out;
  }

  private maskedSecrets(engineId: ConnectorEngineId, encrypted: Record<string, string>): Record<string, string> {
    const secretKeys = secretFieldKeys(engineId);
    const out: Record<string, string> = {};
    for (const key of secretKeys) {
      if (encrypted?.[key]) out[key] = MASK;
    }
    return out;
  }

  private shape(row: any) {
    const engineId = toEngineId(row.engine);
    return {
      id: row.id,
      name: row.name,
      engine: engineId,
      config: row.config,
      secrets: this.maskedSecrets(engineId, row.secrets as Record<string, string>),
      status: row.status,
      lastTestAt: row.lastTestAt,
      lastTestOk: row.lastTestOk,
      lastTestMsg: row.lastTestMsg,
      lastSyncedAt: row.lastSyncedAt,
      syncInterval: row.syncInterval,
      datasetCount: row._count?.datasets ?? row.datasets?.length ?? 0,
    };
  }

  async list() {
    const rows = await this.prisma.connector.findMany({
      include: { _count: { select: { datasets: true } } },
      orderBy: { createdAt: "asc" },
    });
    return rows.map((r) => this.shape(r));
  }

  /** Tests connection details before anything is persisted (the modal's "Test connection" step). */
  async testDraft(dto: SaveConnectorDto) {
    this.validateFields(dto.engine, dto.fields);
    const { config, plainSecrets } = this.splitFields(dto.engine, dto.fields);
    const res = await this.ai.client.post("/internal/connectors/test", {
      engine: dto.engine,
      config,
      secrets: plainSecrets,
    });
    return res.data as { ok: boolean; message: string };
  }

  /** "Connect & discover" — persists the connector, then immediately syncs it. */
  async create(dto: SaveConnectorDto) {
    this.validateFields(dto.engine, dto.fields);
    const { config, plainSecrets } = this.splitFields(dto.engine, dto.fields);
    const secrets = this.encryptSecrets(plainSecrets);

    const row = await this.prisma.connector.create({
      data: {
        name: dto.name?.trim() || `${dto.engine} connector`,
        engine: toEngineEnum(dto.engine),
        config,
        secrets,
        syncInterval: dto.syncInterval || "Manual only",
        status: "SYNCING",
      },
    });

    await this.runSync(row.id, dto.engine, config, plainSecrets);
    return this.findOneShaped(row.id);
  }

  async remove(id: string) {
    const row = await this.prisma.connector.findUnique({ where: { id } });
    if (!row) throw new NotFoundException("Connector not found.");
    await this.prisma.connector.delete({ where: { id } });
    return { ok: true };
  }

  async syncNow(id: string) {
    const row = await this.prisma.connector.findUnique({ where: { id } });
    if (!row) throw new NotFoundException("Connector not found.");
    await this.prisma.connector.update({ where: { id }, data: { status: "SYNCING" } });
    const engineId = toEngineId(row.engine);
    const plainSecrets = this.decryptSecrets(row.secrets as Record<string, string>);
    await this.runSync(id, engineId, row.config as Record<string, string>, plainSecrets);
    return this.findOneShaped(id);
  }

  private async runSync(id: string, engineId: ConnectorEngineId, config: Record<string, string>, secrets: Record<string, string>) {
    try {
      const res = await this.ai.client.post("/internal/connectors/sync", { engine: engineId, config, secrets, connectorId: id });
      const data = res.data as { ok: boolean; message: string; datasets: { name: string; columns: string[]; rowCount: number; sampleRows: string[][] }[] };

      if (!data.ok) {
        await this.prisma.connector.update({
          where: { id },
          data: { status: "ERROR", lastTestOk: false, lastTestMsg: data.message, lastTestAt: new Date() },
        });
        return;
      }

      await this.prisma.$transaction([
        this.prisma.unifiedDataset.deleteMany({ where: { connectorId: id } }),
        ...data.datasets.map((d) =>
          this.prisma.unifiedDataset.create({
            data: {
              connectorId: id,
              name: d.name,
              columns: d.columns,
              rowCount: d.rowCount,
              sampleRows: d.sampleRows,
              status: "synced",
              syncedAt: new Date(),
            },
          }),
        ),
        this.prisma.connector.update({
          where: { id },
          data: { status: "SYNCED", lastSyncedAt: new Date(), lastTestOk: true, lastTestMsg: data.message, lastTestAt: new Date() },
        }),
      ]);
    } catch (e: any) {
      await this.prisma.connector.update({
        where: { id },
        data: { status: "ERROR", lastTestOk: false, lastTestMsg: e?.message ?? "Sync failed.", lastTestAt: new Date() },
      });
    }
  }

  private async findOneShaped(id: string) {
    const row = await this.prisma.connector.findUniqueOrThrow({ where: { id }, include: { _count: { select: { datasets: true } } } });
    return this.shape(row);
  }

  // ── Unified Data Store / Catalog ──

  async catalog() {
    const rows = await this.prisma.unifiedDataset.findMany({
      include: { connector: { select: { name: true, engine: true } } },
      orderBy: { name: "asc" },
    });
    return rows.map((r) => ({
      id: r.id,
      name: r.name,
      connectorId: r.connectorId,
      connectorName: r.connector.name,
      connectorEngine: toEngineId(r.connector.engine),
      columns: r.columns as string[],
      rowCount: r.rowCount,
      status: r.status,
      syncedAt: r.syncedAt,
    }));
  }

  async tablePreview(id: string) {
    const row = await this.prisma.unifiedDataset.findUnique({ where: { id }, include: { connector: { select: { name: true } } } });
    if (!row) throw new NotFoundException("Table not found.");
    return {
      id: row.id,
      name: row.name,
      connectorName: row.connector.name,
      columns: row.columns as string[],
      rowCount: row.rowCount,
      sampleRows: (row.sampleRows as string[][]) ?? [],
      status: row.status,
    };
  }
}
