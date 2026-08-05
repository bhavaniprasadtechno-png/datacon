export { PrismaClient } from "@prisma/client";

export const ConnectorEngine = {
  SQLITE: "SQLITE",
  POSTGRES: "POSTGRES",
  SUPABASE: "SUPABASE",
  MYSQL: "MYSQL",
  MONGODB: "MONGODB",
  HTTP: "HTTP",
  BIGQUERY: "BIGQUERY",
  SNOWFLAKE: "SNOWFLAKE",
  S3: "S3",
  AZURE: "AZURE",
  GCS: "GCS",
} as const;

export type ConnectorEngine = (typeof ConnectorEngine)[keyof typeof ConnectorEngine];

export const ConnectorStatus = {
  SYNCED: "SYNCED",
  SYNCING: "SYNCING",
  ERROR: "ERROR",
  PENDING: "PENDING",
} as const;

export type ConnectorStatus = (typeof ConnectorStatus)[keyof typeof ConnectorStatus];

export const DocType = {
  PDF: "PDF",
  CSV: "CSV",
  TXT: "TXT",
  MD: "MD",
} as const;

export type DocType = (typeof DocType)[keyof typeof DocType];

export const DocStatus = {
  UPLOADING: "UPLOADING",
  CHUNKING: "CHUNKING",
  INDEXING: "INDEXING",
  INDEXED: "INDEXED",
  FAILED: "FAILED",
} as const;

export type DocStatus = (typeof DocStatus)[keyof typeof DocStatus];

export const Intent = {
  DESCRIPTIVE: "DESCRIPTIVE",
  DIAGNOSTIC: "DIAGNOSTIC",
  PREDICTIVE: "PREDICTIVE",
  PRESCRIPTIVE: "PRESCRIPTIVE",
} as const;

export type Intent = (typeof Intent)[keyof typeof Intent];

export const AccountStatus = {
  ACTIVE: "ACTIVE",
  SUSPENDED: "SUSPENDED",
} as const;

export type AccountStatus = (typeof AccountStatus)[keyof typeof AccountStatus];
