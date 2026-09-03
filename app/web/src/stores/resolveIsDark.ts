export type DarkModeMode = "light" | "dark" | "system";

export function resolveIsDark(mode: DarkModeMode, prefersDark: boolean): boolean {
  if (mode === "system") return prefersDark;
  return mode === "dark";
}
