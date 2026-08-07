import { IsIn, IsObject, IsOptional, IsString, MinLength } from "class-validator";

const DASHLET_INTENTS = ["descriptive", "diagnostic", "predictive", "prescriptive"] as const;
export type DashletIntent = (typeof DASHLET_INTENTS)[number];

export class SaveDashletDto {
  @IsOptional()
  @IsString()
  dashboardId?: string;

  @IsOptional()
  @IsString()
  @MinLength(1)
  name?: string;

  @IsString()
  @MinLength(1)
  title!: string;

  @IsString()
  text!: string;

  @IsIn(DASHLET_INTENTS)
  intent!: DashletIntent;

  @IsObject()
  payload!: Record<string, unknown>;
}
