import { IsString, MinLength } from "class-validator";

export class CompleteRegistrationDto {
  @IsString()
  @MinLength(1)
  name!: string;

  @IsString()
  @MinLength(1)
  orgName!: string;
}
