import { IsEmail, IsString, MinLength } from "class-validator";

export class CreateOrganizationDto {
  @IsString()
  @MinLength(1)
  name!: string;

  @IsEmail()
  adminEmail!: string;

  @IsString()
  @MinLength(1)
  adminName!: string;
}
