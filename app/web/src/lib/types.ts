import type {
  ChatIntent,
  ConnectorEngineId,
  DescriptivePayload,
  DiagnosticPayload,
  PermissionKey,
  PredictivePayload,
  PrescriptivePayload,
} from "@datacon/shared-types";

export type ChatPayload = DescriptivePayload | DiagnosticPayload | PredictivePayload | PrescriptivePayload;

export interface Persona {
  id: string;
  name: string;
  title: string | null;
  initials: string;
  avatarGrad: string;
  roleId: string;
  role: { name: string; colorHex: string | null; bgHex: string | null };
}

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  initials: string;
  avatarGrad: string;
  title: string | null;
  roleId: string;
  roleName: string;
  permissions: PermissionKey[];
}

export interface RbacRole {
  id: string;
  name: string;
  colorHex: string | null;
  bgHex: string | null;
  isSystem: boolean;
  permissions: PermissionKey[];
  userCount: number;
}

export interface RbacUser {
  id: string;
  name: string;
  email: string;
  initials: string;
  avatarGrad: string;
  title: string | null;
  isCore: boolean;
  roleId: string;
  role: RbacRole;
  canDelete: boolean;
  permissionCount: number;
}

export interface PermissionDef {
  key: PermissionKey;
  label: string;
  group: string;
}

export type ConnectorStatus = "SYNCED" | "SYNCING" | "ERROR" | "PENDING";

export interface Connector {
  id: string;
  name: string;
  engine: ConnectorEngineId;
  config: Record<string, string>;
  secrets: Record<string, string>;
  status: ConnectorStatus;
  lastTestAt: string | null;
  lastTestOk: boolean | null;
  lastTestMsg: string | null;
  lastSyncedAt: string | null;
  syncInterval: string;
  datasetCount: number;
}

export interface CatalogEntry {
  id: string;
  name: string;
  connectorId: string;
  connectorName: string;
  connectorEngine: ConnectorEngineId;
  columns: string[];
  rowCount: number;
  status: string;
  syncedAt: string | null;
}

export interface TablePreview {
  id: string;
  name: string;
  connectorName: string;
  columns: string[];
  rowCount: number;
  sampleRows: string[][];
  status: string;
}

export type DocType = "PDF" | "CSV" | "TXT" | "MD";
export type DocStatus = "UPLOADING" | "CHUNKING" | "INDEXING" | "INDEXED" | "FAILED";

export interface DataSourceRecord {
  id: string;
  title: string;
  filename: string;
  type: DocType;
  status: DocStatus;
  sizeBytes: number;
  chunkCount: number | null;
  rowCount: number | null;
  colCount: number | null;
  failureMsg: string | null;
  uploadedBy: string;
  createdAt: string;
}

export interface DataSourcePreview {
  id: string;
  title: string;
  filename: string;
  columns: string[];
  rowCount: number | null;
  sampleRows: string[][];
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  intent: ChatIntent | null;
  text: string;
  payload: ChatPayload | null;
  vote: -1 | 0 | 1;
  streaming?: boolean;
}

export interface ForecastResult {
  model: string;
  horizon: number;
  projected: string;
  ciLow: string;
  ciHigh: string;
  growth: string;
  mape: string;
  series: { label: string; value: number }[];
  topDrivers: { label: string; pct: number }[];
}
