# Request-Scoped Prisma Transaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the two independent Postgres transactions that run on every authenticated API request (one in `SupabaseAuthGuard`'s user lookup, one in each `.scoped.*` Prisma call) into a single shared transaction per request, cutting the measured ~780ms auth+query floor to ~350-450ms.

**Architecture:** A new `RequestTransactionMiddleware`, registered globally ahead of guards/interceptors/the handler, opens one Prisma interactive transaction per request and stores it in a new `AsyncLocalStorage`. `SupabaseAuthGuard` and `PrismaService`'s `.scoped` extension both check that storage first and reuse the open transaction when present, falling back to today's per-call-transaction behavior when absent (tests, background code, and the explicitly excluded `/chat/stream` and `/health` routes).

**Correction made during Task 1 (still 2026-07-29):** the plan originally used a `RequestTransactionGuard` (see spec's own correction note for the full explanation) — a Guard's `canActivate()` can't actually wrap the rest of the pipeline in an ALS context, because Nest calls the next guard/interceptor/handler itself, outside any code the guard controls. A test proved this directly. Middleware works because it gets a `next()` callback the middleware itself invokes. Task 1 below reflects the corrected, already-implemented-and-passing version.

**Tech Stack:** NestJS 10, Prisma 5.22 (`@prisma/client` + generated `@datacon/prisma`), Jest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-29-request-scoped-transaction-design.md` — every task below implements a decision from that doc; re-read it if a task's rationale is unclear.
- `POST /chat/stream` must never be wrapped in a shared transaction (SSE proxy, can run 10s+ — see spec Decision 5).
- Existing tests must keep passing unmodified unless a task explicitly says otherwise — the fallback branch (`requestTxStorage` empty) must behave exactly as today's code.
- No changes to `OrgContextInterceptor` or `orgContextStorage` — untouched per spec.
- Do not commit anything unless the user explicitly asks for it in that turn (project `CLAUDE.md` rule — this overrides any skill's default "commit as you go" guidance).

---

### Task 1: `RequestTransactionMiddleware` + supporting storage — COMPLETE

**Files:**
- Create: `app/api/src/prisma/request-transaction.storage.ts`
- Create: `app/api/src/prisma/request-transaction.middleware.ts`
- Test: `app/api/src/prisma/request-transaction.middleware.spec.ts`

**Interfaces:**
- Produces: `requestTxStorage: AsyncLocalStorage<RequestTx>`, `RequestTx { tx: Prisma.TransactionClient; rlsSet: boolean }` (exported from `request-transaction.storage.ts`) — consumed by Task 2 and Task 3.
- Produces: `RequestTransactionMiddleware` class, constructor `(prisma: PrismaService)`, implements `NestMiddleware` — consumed by Task 4 (registered via `AppModule.configure()`).

- [x] **Step 1: Create the storage file**

```typescript
// app/api/src/prisma/request-transaction.storage.ts
import { AsyncLocalStorage } from "node:async_hooks";
import type { Prisma } from "@prisma/client";

export interface RequestTx {
  tx: Prisma.TransactionClient;
  /** Flips true the first time an org-scoped operation sets the RLS
   * session var on this transaction — set_config(..., true) is
   * transaction-local, so it only needs doing once per request. */
  rlsSet: boolean;
}

/** Populated per-request by RequestTransactionMiddleware; read by
 * SupabaseAuthGuard and PrismaService.scoped's query extension so both
 * reuse the same open transaction/connection instead of each opening
 * their own. */
export const requestTxStorage = new AsyncLocalStorage<RequestTx>();
```

- [x] **Step 2: Write the failing tests for the middleware**

```typescript
// app/api/src/prisma/request-transaction.middleware.spec.ts
import { RequestTransactionMiddleware } from "./request-transaction.middleware";
import { requestTxStorage } from "./request-transaction.storage";
import { PrismaService } from "./prisma.service";

function fakeResponse() {
  const listeners: Record<string, Array<() => void>> = {};
  return {
    headersSent: false,
    once: (event: string, cb: () => void) => {
      (listeners[event] ??= []).push(cb);
    },
    emit: (event: string) => {
      (listeners[event] ?? []).forEach((cb) => cb());
    },
  };
}

describe("RequestTransactionMiddleware", () => {
  it("opens exactly one transaction and makes it available via requestTxStorage while next() runs", () => {
    const fakeTx = { marker: "the-shared-tx" };
    const txFn = jest.fn((cb: (tx: unknown) => unknown) => cb(fakeTx));
    const prisma = { $transaction: txFn } as unknown as PrismaService;
    const middleware = new RequestTransactionMiddleware(prisma);
    const res = fakeResponse();

    let storeSeenInsideNext: unknown;
    const next = jest.fn(() => {
      storeSeenInsideNext = requestTxStorage.getStore();
    });

    middleware.use({} as never, res as never, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(txFn).toHaveBeenCalledTimes(1);
    expect(storeSeenInsideNext).toEqual({ tx: fakeTx, rlsSet: false });
  });

  it("resolves the transaction once the response finishes", async () => {
    const fakeTx = {};
    let settled = false;
    const txFn = jest.fn((cb: (tx: unknown) => unknown) =>
      Promise.resolve(cb(fakeTx)).then((v) => {
        settled = true;
        return v;
      }),
    );
    const prisma = { $transaction: txFn } as unknown as PrismaService;
    const middleware = new RequestTransactionMiddleware(prisma);
    const res = fakeResponse();

    middleware.use({} as never, res as never, jest.fn());
    await new Promise((r) => setImmediate(r));
    expect(settled).toBe(false);

    res.emit("finish");
    await new Promise((r) => setImmediate(r));
    expect(settled).toBe(true);
  });

  it("calls next(err) if the transaction can't be opened at all", async () => {
    const err = new Error("pool exhausted");
    const txFn = jest.fn(() => Promise.reject(err));
    const prisma = { $transaction: txFn } as unknown as PrismaService;
    const middleware = new RequestTransactionMiddleware(prisma);
    const res = fakeResponse();
    const next = jest.fn();

    middleware.use({} as never, res as never, next);
    await new Promise((r) => setImmediate(r));

    expect(next).toHaveBeenCalledWith(err);
  });
});
```

Run: `cd app/api && npx jest src/prisma/request-transaction.middleware.spec.ts` — confirmed FAIL first ("Cannot find module").

- [x] **Step 3: Implement the middleware**

```typescript
// app/api/src/prisma/request-transaction.middleware.ts
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
      .$transaction((tx) =>
        requestTxStorage.run({ tx, rlsSet: false }, () => {
          next();
          return new Promise<void>((resolveTx) => {
            const done = () => resolveTx();
            res.once("finish", done);
            res.once("close", done);
          });
        }),
      )
      .catch((err) => {
        // Only reachable if the transaction itself couldn't even open —
        // once next() has run, any later failure happens after the
        // response is already being handled downstream.
        if (!res.headersSent) next(err);
      });
  }
}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd app/api && npx jest src/prisma/request-transaction.middleware.spec.ts` — PASS (3 tests).

- [x] **Step 5: Type-check**

Run: `cd app/api && npx tsc --noEmit -p tsconfig.json` — no errors.

Not committed — this project's `CLAUDE.md` requires an explicit user request in the same turn before running `git commit`. Changes left staged/unstaged; committing is the user's call, not a plan step.

---

### Task 2: `PrismaService.scoped` reuses the request-scoped transaction

**Files:**
- Modify: `app/api/src/prisma/prisma.service.ts`
- Test: `app/api/src/prisma/prisma.service.spec.ts` (new)

**Interfaces:**
- Consumes: `requestTxStorage` from Task 1.
- Produces: `needsRlsVarSet(reqTx: { rlsSet: boolean }): boolean` (exported for the unit test below) — the one piece of genuinely new branching logic in this file; everything else is straightforward wiring, so it's covered by the type-check plus the real browser re-measurement in Task 4 rather than a Prisma-internals-mocking test (there's no existing precedent in this codebase for unit-testing `$extends` internals directly — every other `.scoped` consumer test mocks at the `PrismaService` boundary instead, see `auth.service.spec.ts`).

- [ ] **Step 1: Write the failing test for the memoization helper**

```typescript
// app/api/src/prisma/prisma.service.spec.ts
import { needsRlsVarSet } from "./prisma.service";

describe("needsRlsVarSet", () => {
  it("returns true exactly once per request-tx store, false after", () => {
    const store = { rlsSet: false };

    expect(needsRlsVarSet(store)).toBe(true);
    expect(store.rlsSet).toBe(true);
    expect(needsRlsVarSet(store)).toBe(false);
    expect(needsRlsVarSet(store)).toBe(false);
  });

  it("two independent stores are tracked independently", () => {
    const a = { rlsSet: false };
    const b = { rlsSet: false };

    expect(needsRlsVarSet(a)).toBe(true);
    expect(needsRlsVarSet(b)).toBe(true);
    expect(needsRlsVarSet(a)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/api && npx jest src/prisma/prisma.service.spec.ts`
Expected: FAIL with "needsRlsVarSet is not a function" (or similar — not yet exported)

- [ ] **Step 3: Modify `prisma.service.ts`**

Current file (for reference — this is the whole file being modified):

```typescript
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
  readonly scoped = withOrgContext(this);

  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
```

Replace it with:

```typescript
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
  readonly scoped = withOrgContext(this);

  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
```

This requires `OrgContext` to be exported from `org-context.storage.ts` — check `app/api/src/prisma/org-context.storage.ts`; it already exports `export interface OrgContext { ... }`, so no change needed there.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app/api && npx jest src/prisma/prisma.service.spec.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Type-check and run the full suite**

Run: `cd app/api && npx tsc --noEmit -p tsconfig.json && npx jest`
Expected: no type errors; all existing tests still pass unmodified (this file's behavioral change only activates when `requestTxStorage` has a store, which nothing sets yet at this point in the plan — Task 1's guard isn't wired into the app until Task 4).

Do not commit — same rule as Task 1.

---

### Task 3: `SupabaseAuthGuard` reuses the shared transaction

**Files:**
- Modify: `app/api/src/auth/guards/supabase-auth.guard.ts`
- Modify: `app/api/src/auth/guards/supabase-auth.guard.spec.ts`

**Interfaces:**
- Consumes: `requestTxStorage` from Task 1.

- [ ] **Step 1: Add the failing test**

Add this test to the existing `describe("SupabaseAuthGuard", ...)` block in `app/api/src/auth/guards/supabase-auth.guard.spec.ts` (alongside the existing tests — don't remove any):

```typescript
import { requestTxStorage } from "../../prisma/request-transaction.storage";

// ...inside describe("SupabaseAuthGuard", () => { ... }), add:

  it("looks up the user on the request-scoped transaction when one is open, instead of a separate query", async () => {
    jest.spyOn(supabaseAdminClient, "getSupabaseAdminClient").mockReturnValue({
      auth: {
        getClaims: jest
          .fn()
          .mockResolvedValue({ data: { claims: { sub: "11111111-1111-1111-1111-111111111111" } }, error: null }),
      },
    } as never);
    const baseFindUnique = jest.fn();
    const txFindUnique = jest.fn().mockResolvedValue({
      id: "11111111-1111-1111-1111-111111111111",
      orgId: "acme-corp",
      roleId: "admin",
      status: "ACTIVE",
      org: { status: "ACTIVE" },
      role: { permissions: [{ permissionKey: "manage_users" }] },
    });
    const prisma = { user: { findUnique: baseFindUnique } } as unknown as PrismaService;
    const guard = new SupabaseAuthGuard(prisma);
    const req: { headers: Record<string, string>; user?: unknown } = { headers: { authorization: "Bearer good" } };
    const ctx = { switchToHttp: () => ({ getRequest: () => req }) } as unknown as ExecutionContext;

    const result = await requestTxStorage.run(
      { tx: { user: { findUnique: txFindUnique } } as never, rlsSet: false },
      () => guard.canActivate(ctx),
    );

    expect(result).toBe(true);
    expect(txFindUnique).toHaveBeenCalledTimes(1);
    expect(baseFindUnique).not.toHaveBeenCalled();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/api && npx jest src/auth/guards/supabase-auth.guard.spec.ts`
Expected: FAIL — `txFindUnique` was never called (guard still always uses `this.prisma.user.findUnique`)

- [ ] **Step 3: Modify the guard**

In `app/api/src/auth/guards/supabase-auth.guard.ts`, add the import and change the lookup:

```typescript
import { requestTxStorage } from "../../prisma/request-transaction.storage";
```

Replace:

```typescript
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      include: { role: { include: { permissions: true } }, org: { select: { status: true } } },
    });
```

with:

```typescript
    const reqTx = requestTxStorage.getStore();
    const client = (reqTx?.tx ?? this.prisma) as unknown as Pick<PrismaService, "user">;
    const user = await client.user.findUnique({
      where: { id: userId },
      include: { role: { include: { permissions: true } }, org: { select: { status: true } } },
    });
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app/api && npx jest src/auth/guards/supabase-auth.guard.spec.ts`
Expected: PASS (all tests, including the 5 pre-existing ones — none should need changes, since they don't populate `requestTxStorage`, so `reqTx` is `undefined` and `client` falls back to `this.prisma` exactly as before)

- [ ] **Step 5: Type-check**

Run: `cd app/api && npx tsc --noEmit -p tsconfig.json`
Expected: no errors

Do not commit — same rule as Task 1.

---

### Task 4: Wire the middleware into the app, exclude streaming and health routes, verify end-to-end

**Files:**
- Modify: `app/api/src/app.module.ts`

**Interfaces:**
- Consumes: `RequestTransactionMiddleware` (Task 1).

This task has no new unit test of its own — it's wiring an already-tested piece into the module graph via Nest's own standard, supported `MiddlewareConsumer.exclude()` API (no code changes needed in `chat.controller.ts` or `health.controller.ts` — exclusion is path-based, configured entirely in `app.module.ts`). Verification is the full existing suite (must stay green) plus the real-number browser re-measurement and manual checks called out in the spec's testing plan, which is the only way to actually confirm the RLS/transaction-sharing behavior against real Postgres (see Task 2's note — this codebase has no precedent for unit-testing `$extends` against a live DB, and inventing one here would be testing Postgres, not our code).

**Note beyond the spec:** `HealthController.check()` (`GET /health`) is unauthenticated, has no `@UseGuards` at all today, and is typically hit frequently by load balancers/uptime checks — wrapping it in a transaction it doesn't need would add pointless overhead to a high-frequency endpoint and hold a pool connection longer than necessary. Excluding it wasn't in the original spec (which only discussed `/chat/stream`) but follows directly from the same rationale, so it's added here.

- [ ] **Step 1: Register the middleware in `app.module.ts`, excluding `/chat/stream` and `/health`**

Current relevant section:

```typescript
import { Module } from "@nestjs/common";
import { APP_INTERCEPTOR } from "@nestjs/core";
```

...

```typescript
  controllers: [HealthController],
  providers: [{ provide: APP_INTERCEPTOR, useClass: OrgContextInterceptor }],
})
export class AppModule {}
```

Change to:

```typescript
import { MiddlewareConsumer, Module, NestModule, RequestMethod } from "@nestjs/common";
import { APP_INTERCEPTOR } from "@nestjs/core";
```

...add the import:

```typescript
import { RequestTransactionMiddleware } from "./prisma/request-transaction.middleware";
```

...leave the `providers` array exactly as-is (no `APP_GUARD` needed — middleware isn't registered as a provider entry), and implement `NestModule`:

```typescript
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
```

- [ ] **Step 2: Type-check and run the full suite**

Run: `cd app/api && npx tsc --noEmit -p tsconfig.json && npx jest`
Expected: no type errors; all tests pass (existing + the new ones from Tasks 1-3)

Do not commit — same rule as Task 1. Once all four tasks and the manual verification below are done, ask the user whether they want everything committed (and how — one commit per task, or one commit for the whole feature).

- [ ] **Step 3: Manual verification against the running app**

1. Start the API (`npm run start:dev` or the project's usual dev command) against the real Supabase-backed database.
2. Repeat the exact real-number browser trace used for the baseline earlier: open the app, clear `performance.clearResourceTimings()` in the console, click a conversation, then read `performance.getEntriesByType('resource')` filtered to `/api/` and check the `/chat/messages` entry's duration. Expect it to drop from the ~1.45-1.55s baseline toward ~350-450ms.
3. Confirm `/chat/stream` still works end-to-end: send a chat message, confirm tokens stream in and the conversation/message rows persist correctly afterward.
4. Confirm an invalid/expired bearer token on a non-streaming route (e.g. `GET /users` with a garbage token) still returns 401 — proves the transaction rollback path works correctly on guard failure.
5. Confirm `GET /health` still returns `{ status: "ok", db: "up", ... }`.

---

## Explicitly out of scope (per spec)

- Frontend refetch-storm fix (React Query `refetchOnWindowFocus` + Supabase auto-refresh).
- Decoupling the Sidebar's global `useConversations()` call from every page load.
- Reducing the per-transaction Postgres round-trip count itself (`BEGIN`/`DEALLOCATE ALL`/`SET_CONFIG`/query/`COMMIT`).
- Prisma `connection_limit`/pool tuning.
- Reapplying the stashed guard-cache fix (`git stash list` still has it) — superseded by this approach.
