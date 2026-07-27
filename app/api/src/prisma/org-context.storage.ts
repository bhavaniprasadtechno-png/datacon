import { AsyncLocalStorage } from "node:async_hooks";

export interface OrgContext {
  orgId?: string;
  isPlatformAdmin?: boolean;
}

/** Populated per-request by OrgContextInterceptor; read by
 * PrismaService.scoped's query extension (this file's sibling,
 * prisma.service.ts) to set the matching Postgres RLS session variable. */
export const orgContextStorage = new AsyncLocalStorage<OrgContext>();
