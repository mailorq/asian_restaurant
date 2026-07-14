import { useState } from "react";
import { Modal } from "./Modal";
import { Icon } from "./Icon";
import { useUI } from "../stores/ui";
import { useToast } from "../stores/toast";

function Field({
  label,
  children,
  required,
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-muted">
        {label}
        {required && <span className="text-accent"> *</span>}
      </span>
      {children}
    </label>
  );
}

const inputCls =
  "h-11 w-full rounded-xl border border-border bg-surface-2 px-3.5 text-text placeholder:text-muted/70 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

export function AuthModal() {
  const tab = useUI((s) => s.authTab);
  const setTab = (t: "login" | "register") => useUI.setState({ authTab: t });
  const close = useUI((s) => s.closeModal);
  const notify = useToast((s) => s.notify);
  const [showPassword, setShowPassword] = useState(false);

  const isLogin = tab === "login";

  function submit(e: React.FormEvent) {
    e.preventDefault();
    notify(isLogin ? "Вход выполнен" : "Регистрация успешна");
    close();
  }

  return (
    <Modal title={isLogin ? "Вход" : "Регистрация"} onClose={close}>
      <div className="mb-5 grid grid-cols-2 gap-1 rounded-full bg-surface-2 p-1">
        {(["login", "register"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-full py-2 text-sm font-medium transition-colors ${
              tab === t ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text"
            }`}
          >
            {t === "login" ? "Вход" : "Регистрация"}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Имя пользователя" required>
          <input className={inputCls} placeholder="ivan" autoComplete="username" required />
        </Field>

        {!isLogin && (
          <Field label="Телефон" required>
            <input
              type="tel"
              className={inputCls}
              placeholder="+7 900 000-00-00"
              autoComplete="tel"
              required
            />
          </Field>
        )}

        <Field label="Пароль" required>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              className={`${inputCls} pr-11`}
              placeholder="••••••••"
              autoComplete={isLogin ? "current-password" : "new-password"}
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
              className="absolute right-2 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg text-muted hover:text-text"
            >
              <Icon name={showPassword ? "moon" : "sun"} size={17} />
            </button>
          </div>
        </Field>

        <button
          type="submit"
          className="mt-1 h-11 rounded-xl bg-primary font-medium text-primary-contrast transition-[background-color,transform] duration-200 hover:bg-primary-hover active:scale-[0.98]"
        >
          {isLogin ? "Войти" : "Создать аккаунт"}
        </button>
      </form>

      <p className="mt-4 text-center text-sm text-muted">
        {isLogin ? "Нет аккаунта? " : "Уже с нами? "}
        <button
          onClick={() => setTab(isLogin ? "register" : "login")}
          className="font-medium text-accent hover:underline"
        >
          {isLogin ? "Зарегистрироваться" : "Войти"}
        </button>
      </p>
    </Modal>
  );
}
