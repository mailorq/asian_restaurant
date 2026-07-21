import { useState } from "react";
import { Icon } from "../components/Icon";
import { ThemeToggle } from "../components/ThemeToggle";
import { useUI } from "../stores/ui";
import { useAuth } from "../stores/auth";
import { EmployeeOrders } from "../components/employee/EmployeeOrders";
import { EmployeeInventory } from "../components/employee/EmployeeInventory";
import { EmployeeUsers } from "../components/employee/EmployeeUsers";

type Tab = "orders" | "inventory" | "users";

const TABS: { value: Tab; label: string; icon: string }[] = [
  { value: "orders", label: "Заказы", icon: "cart" },
  { value: "inventory", label: "Инвентарь", icon: "bowl" },
  { value: "users", label: "Пользователи", icon: "user" },
];

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-bg px-4 text-center">
      <div>{children}</div>
    </div>
  );
}

export function EmployeePage() {
  const ready = useAuth((s) => s.ready);
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  const navigate = useUI((s) => s.navigate);
  const openModal = useUI((s) => s.openModal);
  const [tab, setTab] = useState<Tab>("orders");

  if (!ready) {
    return (
      <Centered>
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent" />
      </Centered>
    );
  }

  if (!user) {
    return (
      <Centered>
        <p className="font-medium">Войдите как сотрудник</p>
        <button
          onClick={() => openModal("auth", "login")}
          className="mt-4 rounded-full bg-primary px-6 py-2.5 text-sm font-medium text-primary-contrast hover:bg-primary-hover"
        >
          Войти
        </button>
      </Centered>
    );
  }

  if (!user.is_employee) {
    return (
      <Centered>
        <p className="font-medium">Нет доступа к панели сотрудника</p>
        <button
          onClick={() => navigate({ name: "home" })}
          className="mt-4 rounded-full border border-border px-6 py-2.5 text-sm font-medium text-muted hover:text-text"
        >
          На витрину
        </button>
      </Centered>
    );
  }

  return (
    <div className="min-h-dvh bg-bg">
      <header className="sticky top-0 z-40 border-b border-border bg-bg/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-5xl items-center gap-4 px-4 sm:px-6">
          <button
            onClick={() => navigate({ name: "home" })}
            className="shrink-0 font-display text-lg font-bold tracking-tight"
          >
            Asian<span className="text-accent">.</span>
            <span className="ml-2 text-sm font-medium text-muted">панель</span>
          </button>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <button
              onClick={() => navigate({ name: "home" })}
              className="hidden rounded-full border border-border px-4 py-2 text-sm font-medium text-muted transition-colors hover:text-text sm:block"
            >
              На витрину
            </button>
            <button
              onClick={() => logout().then(() => navigate({ name: "home" }))}
              className="flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm font-medium text-danger transition-colors hover:bg-danger/10"
            >
              <Icon name="logout" size={16} /> Выйти
            </button>
          </div>
        </div>
      </header>

      <nav className="border-b border-border">
        <div className="mx-auto flex max-w-5xl gap-1 px-4 sm:px-6">
          {TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTab(t.value)}
              className={`flex items-center gap-2 border-b-2 px-3.5 py-3 text-sm font-medium transition-colors ${
                tab === t.value
                  ? "border-accent text-text"
                  : "border-transparent text-muted hover:text-text"
              }`}
            >
              <Icon name={t.icon} size={16} /> {t.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        {tab === "orders" && <EmployeeOrders />}
        {tab === "inventory" && <EmployeeInventory />}
        {tab === "users" && <EmployeeUsers />}
      </main>
    </div>
  );
}
