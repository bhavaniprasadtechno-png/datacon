import { Injectable, NestMiddleware } from "@nestjs/common";
import type { NextFunction, Request, Response } from "express";
import { PrismaService } from "./prisma.service";
import { requestTxStorage } from "./request-transaction.storage";

/** Opens one Prisma transaction per request and calls `next()` from
 * *inside* it, so the whole downstream pipeline (guards, interceptors,
 * the handler) runs within requestTxStorage's ALS context — Express
 * middleware is the only stage in Nest's pipeline that gets a `next()`
 * callback it invokes itself, which is what makes context propagation
 * actually work here (a Guard's canActivate() can't do this: Nest calls
 * the rest of the pipeline itself, outside any code we control, so
 * nothing we do inside canActivate() can make that later code inherit
 * an ALS context — confirmed the hard way by a failing test).
 *
 * The transaction only resolves once the HTTP response finishes,
 * committing everything the request did on the shared connection. */
@Injectable()
export class RequestTransactionMiddleware implements NestMiddleware {
  constructor(private readonly prisma: PrismaService) {}

  use(req: Request, res: Response, next: NextFunction) {
    this.prisma
      .$transaction(
        (tx) =>
          requestTxStorage.run({ tx, rlsSet: false }, () => {
            next();
            return new Promise<void>((resolveTx) => {
              const done = () => resolveTx();
              res.once("finish", done);
              res.once("close", done);
            });
          }),
        { maxWait: 10000, timeout: 60000 },
      )

      .catch((err) => {
        // Only reachable if the transaction itself couldn't even open —
        // once next() has run, any later failure happens after the
        // response is already being handled downstream.
        if (!res.headersSent) next(err);
      });
  }
}
