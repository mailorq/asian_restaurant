import { create } from "zustand";

export type View =
  | { name: "home" }
  | { name: "menu" }
  | { name: "product"; id: number }
  | { name: "orders" }
  | { name: "employee" };
export type ModalName = "auth" | "cart" | null;
export type AuthTab = "login" | "register";
export type Theme = "light" | "dark";

function viewToPath(view: View): string {
  switch (view.name) {
    case "menu":
      return "/menu";
    case "orders":
      return "/orders";
    case "employee":
      return "/employee";
    case "product":
      return `/product/${view.id}`;
    default:
      return "/";
  }
}

function pathToView(path: string): View {
  if (path === "/menu") return { name: "menu" };
  if (path === "/orders") return { name: "orders" };
  if (path === "/employee") return { name: "employee" };
  const product = path.match(/^\/product\/(\d+)$/);
  if (product) return { name: "product", id: Number(product[1]) };
  return { name: "home" };
}

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

  window.addEventListener("popstate", () => set({ view: pathToView(window.location.pathname) }));

  return {
    view: pathToView(window.location.pathname),
    modal: null,
    authTab: "login",
    theme,
    navigate: (view) => {
      if (viewToPath(view) !== window.location.pathname) {
        window.history.pushState({}, "", viewToPath(view));
      }
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
