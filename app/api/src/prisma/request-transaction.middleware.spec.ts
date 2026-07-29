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
