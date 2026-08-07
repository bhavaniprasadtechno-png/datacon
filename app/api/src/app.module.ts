import { MiddlewareConsumer, Module, NestModule, RequestMethod } from "@nestjs/common";
import { APP_INTERCEPTOR } from "@nestjs/core";
import { ConfigModule } from "@nestjs/config";
import { PrismaModule } from "./prisma/prisma.module";
import { CommonModule } from "./common/common.module";
import { HealthController } from "./health/health.controller";
import { AuthModule } from "./auth/auth.module";
import { UsersModule } from "./users/users.module";
import { RolesModule } from "./roles/roles.module";
import { PermissionsModule } from "./permissions/permissions.module";
import { ConnectorsModule } from "./connectors/connectors.module";
import { DocumentsModule } from "./documents/documents.module";
import { MetricsModule } from "./metrics/metrics.module";
import { ChatModule } from "./chat/chat.module";
import { ForecastsModule } from "./forecasts/forecasts.module";
import { InsightsModule } from "./insights/insights.module";
import { DashboardsModule } from "./dashboards/dashboards.module";
import { PlatformAdminModule } from "./platform-admin/platform-admin.module";
import { OrgContextInterceptor } from "./prisma/org-context.interceptor";
import { RequestTransactionMiddleware } from "./prisma/request-transaction.middleware";

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    PrismaModule,
    CommonModule,
    AuthModule,
    UsersModule,
    RolesModule,
    PermissionsModule,
    ConnectorsModule,
    DocumentsModule,
    MetricsModule,
    ChatModule,
    ForecastsModule,
    InsightsModule,
    DashboardsModule,
    PlatformAdminModule,
  ],
  controllers: [HealthController],
  providers: [{ provide: APP_INTERCEPTOR, useClass: OrgContextInterceptor }],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer
      .apply(RequestTransactionMiddleware)
      .exclude(
        { path: "chat/stream", method: RequestMethod.POST },
        { path: "health", method: RequestMethod.GET },
      )
      .forRoutes("*");
  }
}
