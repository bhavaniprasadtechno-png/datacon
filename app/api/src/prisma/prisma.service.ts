import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";
import { PrismaClient } from "@datacon/prisma";
import { orgContextStorage } from "./org-context.storage";

function withOrgContext(client: PrismaClient) {
  return client.$extends({
    name: "org-context",
    query: {
      $allModels: {
        async $allOperations({ model, operation, args, query }) {
          const ctx = orgContextStorage.getStore();
          if (!ctx || (!ctx.orgId && !ctx.isPlatformAdmin)) return query(args);

          return client.$transaction(async (tx) => {
            if (ctx.isPlatformAdmin) {
              await tx.$executeRaw`SELECT set_config('app.is_platform_admin', 'true', true)`;
            } else {
              await tx.$executeRaw`SELECT set_config('app.current_org_id', ${ctx.orgId}, true)`;
            }
            return (tx as unknown as Record<string, Record<string, (a: unknown) => unknown>>)[model!][operation](args);
          });
        },
      },
    },
  });
}

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  /** Org-scoped client — every query runs with the current request's RLS
   * session variable set. Services must use `this.prisma.scoped.<model>`,
   * never `this.prisma.<model>` directly, for anything org-scoped. */
  readonly scoped = withOrgContext(this);

  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
