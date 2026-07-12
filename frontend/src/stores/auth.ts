import { create } from "zustand";

import { api } from "@/api/client";

export interface CurrentUser {
  username: string;
  phone: string | null;
}

interface AuthState {
  user: CurrentUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: false,
  refresh: async () => {
    set({ loading: true });
    try {
      const user = await api<CurrentUser>("/auth/me");
      set({ user, loading: false });
    } catch {
      set({ user: null, loading: false });
    }
  },
}));
