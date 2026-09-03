import { describe, expect, it } from "vitest";
import { resolveIsDark } from "./resolveIsDark";

describe("resolveIsDark", () => {
  it("is dark when mode is 'dark', regardless of system preference", () => {
    expect(resolveIsDark("dark", false)).toBe(true);
  });

  it("is light when mode is 'light', regardless of system preference", () => {
    expect(resolveIsDark("light", true)).toBe(false);
  });

  it("follows the system preference when mode is 'system'", () => {
    expect(resolveIsDark("system", true)).toBe(true);
    expect(resolveIsDark("system", false)).toBe(false);
  });
});
