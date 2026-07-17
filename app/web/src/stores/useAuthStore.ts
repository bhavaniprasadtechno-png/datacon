import { create } from "zustand";
import { capsFromPermissions, type Capabilities } from "@datacon/shared-types";
import type { CurrentUser } from "../lib/types";
import { api } from "../api/client";
import { queryClient } from "../lib/queryClient";

const EMPTY_CAPS = capsFromPermissions([]);

interface AuthState {
  user: CurrentUser | undefined;
  caps: Capabilities;
  isLoading: boolean;
  isAuthenticated: boolean;
  fetchUser: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  quickLogin: (personaId: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: undefined,
  caps: EMPTY_CAPS,
  isLoading: true,
  isAuthenticated: false,
  fetchUser: async () => {
    try {
      const res = await api.get<CurrentUser>("/auth/me");
      set({
        user: res.data,
        caps: capsFromPermissions(res.data.permissions),
        isAuthenticated: true,
        isLoading: false,
      });
    } catch {
      set({
        user: undefined,
        caps: EMPTY_CAPS,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },
  login: async (email, password) => {
    await api.post("/auth/login", { email, password });
    await get().fetchUser();
  },
  register: async (name, email, password) => {
    await api.post("/auth/register", { name, email, password });
    await get().fetchUser();
  },
  quickLogin: async (personaId) => {
    await api.post("/auth/quick-login", { personaId });
    await get().fetchUser();
  },
  logout: async () => {
    await api.post("/auth/logout");
    set({
      user: undefined,
      caps: EMPTY_CAPS,
      isAuthenticated: false,
    });
    queryClient.clear();
  },
}));

export function useAuth() {
  const user = useAuthStore((state) => state.user);
  const caps = useAuthStore((state) => state.caps);
  const isLoading = useAuthStore((state) => state.isLoading);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const login = useAuthStore((state) => state.login);
  const register = useAuthStore((state) => state.register);
  const quickLogin = useAuthStore((state) => state.quickLogin);
  const logout = useAuthStore((state) => state.logout);

  return {
    user,
    caps,
    isLoading,
    isAuthenticated,
    login,
    register,
    quickLogin,
    logout,
  };
}
