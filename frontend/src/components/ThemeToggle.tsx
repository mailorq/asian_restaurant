import { Icon } from "./Icon";
import { useUI } from "../stores/ui";

export function ThemeToggle() {
  const theme = useUI((s) => s.theme);
  const toggle = useUI((s) => s.toggleTheme);

  return (
    <button
      onClick={toggle}
      aria-label={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
      className="grid h-10 w-10 place-items-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <Icon name={theme === "dark" ? "sun" : "moon"} size={20} />
    </button>
  );
}
