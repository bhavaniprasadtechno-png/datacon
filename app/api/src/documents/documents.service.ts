import { BadRequestException, Injectable, Logger, NotFoundException } from "@nestjs/common";
import { DocType } from "@datacon/prisma";
import * as path from "path";
import { PrismaService } from "../prisma/prisma.service";
import { AiClientService } from "../common/ai-client.service";

const MAX_BYTES = 10 * 1024 * 1024; // 10MB, per PRD FR-3.1
const EXT_TO_TYPE: Record<string, DocType> = { pdf: "PDF", csv: "CSV", txt: "TXT", md: "MD" };

@Injectable()
export class DocumentsService {
  private readonly logger = new Logger(DocumentsService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly ai: AiClientService,
  ) {}

  private shape(row: any) {
    return {
      id: row.id,
      title: row.title,
      filename: row.filename,
      type: row.type,
      status: row.status,
      sizeBytes: row.sizeBytes,
      chunkCount: row.chunkCount,
      rowCount: row.rowCount,
      colCount: row.colCount,
      failureMsg: row.failureMsg,
      uploadedBy: row.uploadedBy?.email,
      createdAt: row.createdAt,
    };
  }

  async list() {
    const rows = await this.prisma.dataSource.findMany({
      include: { uploadedBy: { select: { email: true } } },
      orderBy: { createdAt: "desc" },
    });
    return rows.map((r) => this.shape(r));
  }

  async preview(id: string) {
    const row = await this.prisma.dataSource.findUnique({ where: { id } });
    if (!row) throw new NotFoundException("Data source not found.");
    if (!row.columns || !row.sampleRows) {
      throw new NotFoundException("No table preview available for this file — try re-uploading it.");
    }
    return {
      id: row.id,
      title: row.title,
      filename: row.filename,
      columns: row.columns as string[],
      rowCount: row.rowCount,
      sampleRows: row.sampleRows as string[][],
    };
  }

  async remove(id: string) {
    const row = await this.prisma.dataSource.findUnique({ where: { id } });
    if (!row) throw new NotFoundException("Data source not found.");

    // Best-effort: clean up the ChromaDB index entry (PDF/TXT/MD only —
    // CSVs were never indexed there, so this is a harmless no-op for them).
    // Don't let the ai service being unreachable block the actual delete.
    try {
      await this.ai.client.delete(`/internal/documents/${id}`);
    } catch (e: any) {
      this.logger.warn(`Failed to remove ${id} from the vector index (deleting the record anyway): ${e?.message ?? e}`);
    }

    await this.prisma.dataSource.delete({ where: { id } });
    return { ok: true };
  }

  async upload(file: Express.Multer.File, uploadedById: string) {
    if (!file) throw new BadRequestException("No file was uploaded.");

    this.logger.log(`[Upload] Received upload request for file: "${file.originalname}" (${file.size} bytes) from user: ${uploadedById}`);

    const ext = path.extname(file.originalname).replace(".", "").toLowerCase();
    const docType = EXT_TO_TYPE[ext];
    if (!docType) {
      this.logger.warn(`[Upload] Rejected upload of unsupported file type: .${ext} ("${file.originalname}")`);
      throw new BadRequestException(
        `.${ext} files aren't supported yet. Datacon ingests PDF, CSV, TXT and MD — export the sheet as CSV and try again.`,
      );
    }
    if (file.size > MAX_BYTES) {
      const mb = (file.size / (1024 * 1024)).toFixed(1);
      this.logger.warn(`[Upload] Rejected file "${file.originalname}" because size ${mb} MB exceeds limit of 10 MB`);
      throw new BadRequestException(
        `${file.originalname} is ${mb} MB — that exceeds the 10 MB per-file limit. Split the export or compress it before uploading.`,
      );
    }

    const title = path.basename(file.originalname, path.extname(file.originalname));
    this.logger.log(`[Upload] Creating DataSource record in Postgres: title="${title}", type=${docType}`);
    const row = await this.prisma.dataSource.create({
      data: {
        title,
        filename: file.originalname,
        type: docType,
        status: docType === "CSV" ? "INDEXING" : "CHUNKING",
        sizeBytes: file.size,
        uploadedById,
      },
    });
    this.logger.log(`[Upload] DataSource created: ID=${row.id}, initial status=${row.status}`);

    try {
      // Sent as bytes, not a local path — api and ai run as separate
      // processes (separate containers in production) with no shared disk.
      this.logger.log(`[Upload] Sending Base64 ingestion request to AI service for document ID=${row.id}...`);
      const res = await this.ai.client.post(
        "/internal/documents/ingest",
        {
          documentId: row.id,
          title,
          filename: file.originalname,
          contentBase64: file.buffer.toString("base64"),
          docType: docType.toLowerCase(),
        },
        { timeout: 120_000 }, // embedding a large PDF's chunks can take longer than the default 30s
      );
      const data = res.data as {
        ok: boolean;
        message: string;
        chunkCount?: number;
        rowCount?: number;
        colCount?: number;
        columns?: string[];
        sampleRows?: string[][];
      };
      
      this.logger.log(`[Upload] AI service successfully parsed document ID=${row.id}. Rows: ${data.rowCount ?? 0}, Columns: ${data.colCount ?? 0}, Chunks: ${data.chunkCount ?? 0}`);

      this.logger.log(`[Upload] Updating DataSource ID=${row.id} status to INDEXED...`);
      const updated = await this.prisma.dataSource.update({
        where: { id: row.id },
        data: {
          status: "INDEXED",
          chunkCount: data.chunkCount ?? null,
          rowCount: data.rowCount ?? null,
          colCount: data.colCount ?? null,
          columns: data.columns ?? undefined,
          sampleRows: data.sampleRows ?? undefined,
        },
        include: { uploadedBy: { select: { email: true } } },
      });
      this.logger.log(`[Upload] DataSource ID=${row.id} is now fully INDEXED`);
      return this.shape(updated);
    } catch (e: any) {
      // A 502/503/504 means the ai service itself is down/unreachable — surface
      // that plainly rather than the raw axios message ("Request failed with
      // status code 502"), which reads like a broken app rather than a
      // transient, retryable condition.
      const gatewayStatus = e?.response?.status;
      const failureMsg =
        gatewayStatus >= 502 && gatewayStatus <= 504
          ? "The AI service is temporarily unavailable — please try uploading again in a moment."
          : (e?.response?.data?.detail ?? e?.message ?? "Indexing failed.");
      
      this.logger.error(`[Upload] Ingestion failed for document ID=${row.id}: ${failureMsg}`);
      const updated = await this.prisma.dataSource.update({
        where: { id: row.id },
        data: { status: "FAILED", failureMsg },
        include: { uploadedBy: { select: { email: true } } },
      });
      return this.shape(updated);
    }
  }
}
