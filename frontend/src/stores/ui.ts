import { create } from "zustand";

export type View = { name: "home" } | { name: "menu" } | { name: "product"; id: number };
export type ModalName = "auth" | "cart" | "orders" | null;
export type AuthTab = "login" | "register";
export type Theme = "light" | "dark";

interface UIState {
  view: View;
  modal: ModalName;
  authTab: AuthTab;
  theme: Theme;
  navigate: (view: View) => void;
  openModal: (modal: Exclude<ModalName, null>, authTab?: AuthTab) => void;
  closeModal: () => void;
  toggleTheme: () => void;
}

function initialTheme(): Theme {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("theme", theme);
}

export const useUI = create<UIState>((set, get) => {
  const theme = initialTheme();
  applyTheme(theme);

  return {
    view: { name: "home" },
    modal: null,
    authTab: "login",
    theme,
    navigate: (view) => {
      set({ view });
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    openModal: (modal, authTab) => set({ modal, ...(authTab ? { authTab } : {}) }),
    closeModal: () => set({ modal: null }),
    toggleTheme: () => {
      const next = get().theme === "dark" ? "light" : "dark";
      applyTheme(next);
      set({ theme: next });
    },
  };
});
