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
