import { create } from "zustand";
import { capsFromPermissions, type Capabilities } from "@datacon/shared-types";
import type { CurrentUser } from "../lib/types";
import { api } from "../api/client";
import { queryClient } from "../lib/queryClient";
import { supabase } from "../lib/supabaseClient";

const EMPTY_CAPS = capsFromPermissions([]);

interface AuthState {
  user: CurrentUser | undefined;
  caps: Capabilities;
  isLoading: boolean;
  isAuthenticated: boolean;
  fetchUser: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string, orgName: string) => Promise<void>;
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
        caps: res.data.kind === "org_member" ? capsFromPermissions(res.data.permissions) : EMPTY_CAPS,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch {
      set({ user: undefined, caps: EMPTY_CAPS, isAuthenticated: false, isLoading: false });
    }
  },
  login: async (email, password) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    await get().fetchUser();
  },
  register: async (name, email, password, orgName) => {
    const { error } = await supabase.auth.signUp({ email, password, options: { data: { name } } });
    if (error) throw error;
    await api.post("/auth/complete-registration", { name, orgName });
    await get().fetchUser();
  },
  logout: async () => {
    await supabase.auth.signOut();
    set({ user: undefined, caps: EMPTY_CAPS, isAuthenticated: false });
    queryClient.clear();
  },
}));

supabase.auth.onAuthStateChange(() => {
  useAuthStore.getState().fetchUser();
});

export function useAuth() {
  const user = useAuthStore((state) => state.user);
  const caps = useAuthStore((state) => state.caps);
  const isLoading = useAuthStore((state) => state.isLoading);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const login = useAuthStore((state) => state.login);
  const register = useAuthStore((state) => state.register);
  const logout = useAuthStore((state) => state.logout);

  return { user, caps, isLoading, isAuthenticated, login, register, logout };
}
