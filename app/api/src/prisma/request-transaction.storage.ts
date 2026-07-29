import { AsyncLocalStorage } from "node:async_hooks";
import type { Prisma } from "@prisma/client";

export interface RequestTx {
  tx: Prisma.TransactionClient;
  /** Flips true the first time an org-scoped operation sets the RLS
   * session var on this transaction — set_config(..., true) is
   * transaction-local, so it only needs doing once per request. */
  rlsSet: boolean;
}

/** Populated per-request by RequestTransactionGuard; read by
 * SupabaseAuthGuard and PrismaService.scoped's query extension so both
 * reuse the same open transaction/connection instead of each opening
 * their own. */
export const requestTxStorage = new AsyncLocalStorage<RequestTx>();
