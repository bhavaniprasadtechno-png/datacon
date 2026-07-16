import { IsIn, IsObject, IsOptional, IsString, MinLength } from "class-validator";
import type { ConnectorEngineId } from "@datacon/shared-types";

const ENGINE_IDS: ConnectorEngineId[] = ["sqlite", "postgres", "supabase", "mysql", "mongodb", "http", "bigquery", "snowflake"];

export class SaveConnectorDto {
  @IsOptional()
  @IsString()
  @MinLength(1)
  name?: string;

  @IsIn(ENGINE_IDS)
  engine!: ConnectorEngineId;

  /** Flat map of every field key (primary + secondary) from the engine's form to its submitted value. */
  @IsObject()
  fields!: Record<string, string>;

  @IsOptional()
  @IsString()
  syncInterval?: string;
}
