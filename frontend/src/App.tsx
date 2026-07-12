import { useState } from "react";

export default function App() {
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
  }

  return (
    <main className="min-h-screen bg-bg text-text">
      <header className="flex items-center justify-between border-b border-border bg-surface px-8 py-4">
        <h1 className="text-2xl font-bold">Asian Restaurant</h1>
        <button
          onClick={toggleTheme}
          className="rounded-lg bg-primary px-4 py-2 text-primary-contrast transition hover:opacity-80"
        >
          Тема: {theme}
        </button>
      </header>

      <section className="mx-auto max-w-3xl p-8">
        <p className="text-muted">
          Каркас архітектури готовий. Наступний крок — доменні моделі та API.
        </p>
      </section>
    </main>
  );
}
