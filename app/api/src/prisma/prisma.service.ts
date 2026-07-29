import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";
import { PrismaClient } from "@datacon/prisma";
import type { Prisma } from "@prisma/client";
import { orgContextStorage, OrgContext } from "./org-context.storage";
import { requestTxStorage, RequestTx } from "./request-transaction.storage";

/** Returns true exactly once per request-tx store — the RLS session var
 * only needs setting the first time a scoped operation runs against that
 * transaction, since set_config(..., true) is transaction-local and
 * persists for every later statement on the same transaction. */
export function needsRlsVarSet(reqTx: Pick<RequestTx, "rlsSet">): boolean {
  if (reqTx.rlsSet) return false;
  reqTx.rlsSet = true;
  return true;
}

async function setRlsVar(ctx: OrgContext, tx: Prisma.TransactionClient) {
  if (ctx.isPlatformAdmin) {
    await tx.$executeRaw`SELECT set_config('app.is_platform_admin', 'true', true)`;
  } else {
    await tx.$executeRaw`SELECT set_config('app.current_org_id', ${ctx.orgId}, true)`;
  }
}

function withOrgContext(client: PrismaClient) {
  return client.$extends({
    name: "org-context",
    query: {
      $allModels: {
        async $allOperations({ model, operation, args, query }) {
          const ctx = orgContextStorage.getStore();
          if (!ctx || (!ctx.orgId && !ctx.isPlatformAdmin)) return query(args);

          const reqTx = requestTxStorage.getStore();
          if (reqTx) {
            if (needsRlsVarSet(reqTx)) await setRlsVar(ctx, reqTx.tx);
            return (reqTx.tx as unknown as Record<string, Record<string, (a: unknown) => unknown>>)[model!][operation](args);
          }

          return client.$transaction(async (tx) => {
            await setRlsVar(ctx, tx);
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
