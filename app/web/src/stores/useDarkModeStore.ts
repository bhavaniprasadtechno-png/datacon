import { create } from "zustand";
import { resolveIsDark, type DarkModeMode } from "./resolveIsDark";

export type { DarkModeMode };

interface DarkModeState {
  mode: DarkModeMode;
  setMode: (mode: DarkModeMode) => void;
  initialize: () => void;
}

const STORAGE_MODE = "datacon:darkMode";
const DEFAULT_MODE: DarkModeMode = "system";

const prefersDarkQuery = () => window.matchMedia("(prefers-color-scheme: dark)");

export const useDarkModeStore = create<DarkModeState>((set) => ({
  mode: (localStorage.getItem(STORAGE_MODE) as DarkModeMode) || DEFAULT_MODE,
  setMode: (mode) => set({ mode }),
  initialize: () => {
    applyDarkMode(useDarkModeStore.getState().mode);
    prefersDarkQuery().addEventListener("change", () => {
      if (useDarkModeStore.getState().mode === "system") applyDarkMode("system");
    });
  },
}));

function applyDarkMode(mode: DarkModeMode) {
  const isDark = resolveIsDark(mode, prefersDarkQuery().matches);
  document.documentElement.classList.toggle("dark", isDark);
  localStorage.setItem(STORAGE_MODE, mode);
}

useDarkModeStore.subscribe((state) => {
  applyDarkMode(state.mode);
});

export function useDarkMode() {
  const mode = useDarkModeStore((state) => state.mode);
  const setMode = useDarkModeStore((state) => state.setMode);
  return { mode, setMode };
}
