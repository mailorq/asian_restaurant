import { create } from "zustand";

import { api } from "../api/client";

export interface CurrentUser {
  id: number;
  phone: string | null;
  name: string;
}

interface AuthState {
  user: CurrentUser | null;
  ready: boolean;
  setUser: (user: CurrentUser | null) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  ready: false,
  setUser: (user) => set({ user }),
  refresh: async () => {
    try {
      const user = await api<CurrentUser>("/auth/me");
      set({ user, ready: true });
    } catch {
      set({ user: null, ready: true });
    }
  },
  logout: async () => {
    try {
      await api("/auth/csrf"); // fresh token for the current session
      await api("/auth/logout", { method: "POST" });
    } catch {
      /* clear locally regardless */
    }
    set({ user: null });
  },
}));
