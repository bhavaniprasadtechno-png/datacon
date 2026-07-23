import { Controller, Get, UseGuards } from "@nestjs/common";
import { AuthService } from "./auth.service";
import { SupabaseAuthGuard } from "./guards/supabase-auth.guard";
import { CurrentUser } from "./decorators/current-user.decorator";
import { AuthenticatedUser } from "./token.types";

@Controller("auth")
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Get("personas")
  personas() {
    return this.auth.personas();
  }

  @UseGuards(SupabaseAuthGuard)
  @Get("me")
  async me(@CurrentUser() user: AuthenticatedUser) {
    return this.auth.me(user.id);
  }
}
