import { Controller, Get, Param, Post, UploadedFile, UseGuards, UseInterceptors } from "@nestjs/common";
import { FileInterceptor } from "@nestjs/platform-express";
import { JwtAuthGuard } from "../auth/guards/jwt-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { DocumentsService } from "./documents.service";

@UseGuards(JwtAuthGuard, PermissionsGuard)
@Controller("documents")
export class DocumentsController {
  constructor(private readonly documents: DocumentsService) {}

  @Get()
  list() {
    return this.documents.list();
  }

  @Get(":id/preview")
  preview(@Param("id") id: string) {
    return this.documents.preview(id);
  }

  @RequirePermissions("upload_docs")
  @Post()
  @UseInterceptors(FileInterceptor("file", { limits: { fileSize: 25 * 1024 * 1024 } }))
  upload(@UploadedFile() file: Express.Multer.File, @CurrentUser() user: AuthenticatedUser) {
    return this.documents.upload(file, user.id);
  }
}
