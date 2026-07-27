import { Body, Controller, Get, Post, Req, UseGuards } from "@nestjs/common";
import { SupabaseTokenGuard } from "./guards/supabase-token.guard";
import { Bootstrapping } from "./decorators/bootstrapping.decorator";
import { AuthService } from "./auth.service";
import { CompleteRegistrationDto } from "./dto/complete-registration.dto";

@Controller("auth")
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @UseGuards(SupabaseTokenGuard)
  @Bootstrapping()
  @Get("me")
  async me(@Req() req: { supabaseUserId: string }) {
    return this.auth.me(req.supabaseUserId);
  }

  @UseGuards(SupabaseTokenGuard)
  @Bootstrapping()
  @Post("complete-registration")
  async completeRegistration(@Req() req: { supabaseUserId: string }, @Body() dto: CompleteRegistrationDto) {
    return this.auth.completeRegistration(req.supabaseUserId, dto.name, dto.orgName);
  }
}
