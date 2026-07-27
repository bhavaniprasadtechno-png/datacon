import { IsEnum } from "class-validator";
import { AccountStatus } from "@datacon/prisma";

export class UpdateStatusDto {
  @IsEnum(AccountStatus)
  status!: AccountStatus;
}
