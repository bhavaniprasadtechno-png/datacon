import raw from "./connector-engines.json";

export type FieldKind = "text" | "password" | "select" | "textarea";

export interface EngineField {
  key: string;
  label: string;
  placeholder: string;
  help?: string;
  required?: boolean;
  secret?: boolean;
  kind?: "select" | "textarea";
  type?: "text" | "password";
  options?: string[];
  default?: string;
}

export interface EngineDef {
  id: string;
  name: string;
  description: string;
  typeLetter: string;
  primary: EngineField;
  secondary: EngineField[];
}

export type ConnectorEngineId = "sqlite" | "postgres" | "mysql" | "mongodb" | "http" | "bigquery" | "snowflake" | "supabase" | "s3" | "azure" | "gcs";

interface ConnectorEnginesFile {
  syncScheduleOptions: string[];
  [engine: string]: EngineDef | string[];
}

const file = raw as unknown as ConnectorEnginesFile;

export const SYNC_SCHEDULE_OPTIONS: string[] = file.syncScheduleOptions;

export const ENGINE_FIELDS: Record<ConnectorEngineId, EngineDef> = {
  sqlite: file.sqlite as EngineDef,
  postgres: file.postgres as EngineDef,
  supabase: file.supabase as EngineDef,
  mysql: file.mysql as EngineDef,
  mongodb: file.mongodb as EngineDef,
  http: file.http as EngineDef,
  bigquery: file.bigquery as EngineDef,
  snowflake: file.snowflake as EngineDef,
  s3: file.s3 as EngineDef,
  azure: file.azure as EngineDef,
  gcs: file.gcs as EngineDef,
};

export const ENGINE_LIST: EngineDef[] = [
  ENGINE_FIELDS.sqlite,
  ENGINE_FIELDS.postgres,
  ENGINE_FIELDS.supabase,
  ENGINE_FIELDS.mysql,
  ENGINE_FIELDS.mongodb,
  ENGINE_FIELDS.http,
  ENGINE_FIELDS.bigquery,
  ENGINE_FIELDS.snowflake,
  ENGINE_FIELDS.s3,
  ENGINE_FIELDS.azure,
  ENGINE_FIELDS.gcs,
];

export function allFields(engine: ConnectorEngineId): EngineField[] {
  const def = ENGINE_FIELDS[engine];
  return [def.primary, ...def.secondary];
}

export function secretFieldKeys(engine: ConnectorEngineId): string[] {
  return allFields(engine)
    .filter((f) => f.secret)
    .map((f) => f.key);
}
