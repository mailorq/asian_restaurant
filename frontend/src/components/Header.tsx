import { useState } from "react";
import { Icon } from "./Icon";
import { SearchBox } from "./SearchBox";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";
import { useUI, type View } from "../stores/ui";
import { useCart } from "../stores/cart";
import { useAuth } from "../stores/auth";
import { formatUaPhone } from "../lib/phone";

const NAV: { label: string; view: View }[] = [
  { label: "Главная", view: { name: "home" } },
  { label: "Меню", view: { name: "menu" } },
];

export function Header() {
  const view = useUI((s) => s.view);
  const navigate = useUI((s) => s.navigate);
  const openModal = useUI((s) => s.openModal);
  const count = useCart((s) => s.lines.reduce((n, l) => n + l.quantity, 0));
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
        <button
          onClick={() => navigate({ name: "home" })}
          className="shrink-0 font-display text-xl font-bold tracking-tight sm:text-2xl"
        >
          Asian<span className="text-accent">.</span>
        </button>

        <nav className="ml-2 hidden items-center gap-1 md:flex">
          {NAV.map((item) => {
            const active = item.view.name === view.name;
            return (
              <button
                key={item.label}
                onClick={() => navigate(item.view)}
                className={`rounded-full px-3.5 py-2 text-sm font-medium transition-colors ${
                  active ? "text-text" : "text-muted hover:text-text"
                }`}
              >
                {item.label}
                {active && <span className="mx-auto mt-0.5 block h-0.5 w-4 rounded-full bg-accent" />}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto hidden lg:block">
          <SearchBox />
        </div>

        <div className="ml-auto flex items-center gap-1 lg:ml-2">
          <ThemeToggle />
          <button
            onClick={() => openModal("orders")}
            aria-label="Мои заказы"
            className="hidden h-10 w-10 place-items-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-text sm:grid"
          >
            <Icon name="clock" size={20} />
          </button>
          <button
            onClick={() => openModal("cart")}
            aria-label="Корзина"
            className="relative grid h-10 w-10 place-items-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-text"
          >
            <Icon name="cart" size={20} />
            {count > 0 && (
              <span className="tnum absolute -right-0.5 -top-0.5 grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-[11px] font-bold text-accent-contrast">
                {count}
              </span>
            )}
          </button>
          {user ? (
            <UserMenu />
          ) : (
            <button
              onClick={() => openModal("auth", "login")}
              className="ml-1 hidden rounded-full border border-border px-4 py-2 text-sm font-medium transition-colors hover:border-accent hover:text-accent sm:block"
            >
              Войти
            </button>
          )}
          <button
            onClick={() => setMobileOpen((v) => !v)}
            aria-label="Меню"
            className="grid h-10 w-10 place-items-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-text md:hidden"
          >
            <Icon name={mobileOpen ? "close" : "menu"} size={22} />
          </button>
        </div>
      </div>

      {mobileOpen && (
        <div className="anim-fade-in border-t border-border bg-bg px-4 py-3 md:hidden">
          <div className="mb-3 lg:hidden">
            <SearchBox />
          </div>
          <div className="flex flex-col">
            {NAV.map((item) => (
              <button
                key={item.label}
                onClick={() => {
                  navigate(item.view);
                  setMobileOpen(false);
                }}
                className="rounded-lg px-3 py-2.5 text-left text-sm font-medium text-muted hover:bg-surface-2 hover:text-text"
              >
                {item.label}
              </button>
            ))}
            {user ? (
              <button
                onClick={() => {
                  logout();
                  setMobileOpen(false);
                }}
                className="mt-1 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-danger hover:bg-surface-2"
              >
                Выйти ({user.name || formatUaPhone(user.phone ?? "")})
              </button>
            ) : (
              <button
                onClick={() => {
                  openModal("auth", "login");
                  setMobileOpen(false);
                }}
                className="mt-1 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-accent hover:bg-surface-2"
              >
                Войти в аккаунт
              </button>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
