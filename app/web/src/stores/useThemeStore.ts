import { create } from "zustand";
import { DEFAULT_CUSTOM_ACCENT, DEFAULT_THEME_ID, type ThemePreset } from "@datacon/shared-types";

type ThemeId = ThemePreset["id"] | "custom";

interface ThemeState {
  themeId: ThemeId;
  customAccent: string;
  setTheme: (id: ThemeId) => void;
  setCustomAccent: (hex: string) => void;
  initialize: () => void;
}

const STORAGE_THEME = "datacon:theme";
const STORAGE_CUSTOM = "datacon:customAccent";

export const useThemeStore = create<ThemeState>((set) => ({
  themeId: (localStorage.getItem(STORAGE_THEME) as ThemeId) || DEFAULT_THEME_ID,
  customAccent: localStorage.getItem(STORAGE_CUSTOM) || DEFAULT_CUSTOM_ACCENT,
  setTheme: (id) => set({ themeId: id }),
  setCustomAccent: (hex) => set({ customAccent: hex, themeId: "custom" }),
  initialize: () => {
    // Calling this triggers the subscriber to apply the current theme stylesheet rules on startup
    const state = useThemeStore.getState();
    applyTheme(state.themeId, state.customAccent);
  },
}));

function applyTheme(themeId: ThemeId, customAccent: string) {
  const root = document.documentElement;
  root.classList.remove("dc-theme-soft", "dc-theme-emerald", "dc-theme-sapphire", "dc-theme-sunset", "dc-theme-custom");
  root.classList.add("dc-theme", `dc-theme-${themeId}`);
  if (themeId === "custom") {
    root.style.setProperty("--ac", customAccent);
  } else {
    root.style.removeProperty("--ac");
  }
  localStorage.setItem(STORAGE_THEME, themeId);
  localStorage.setItem(STORAGE_CUSTOM, customAccent);
}

// DOM Reactive style side-effects outside React render loop
useThemeStore.subscribe((state) => {
  applyTheme(state.themeId, state.customAccent);
});

export function useTheme() {
  const themeId = useThemeStore((state) => state.themeId);
  const customAccent = useThemeStore((state) => state.customAccent);
  const setTheme = useThemeStore((state) => state.setTheme);
  const setCustomAccent = useThemeStore((state) => state.setCustomAccent);

  return { themeId, customAccent, setTheme, setCustomAccent };
}
