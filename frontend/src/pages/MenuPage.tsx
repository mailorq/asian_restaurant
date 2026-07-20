import { useState } from "react";
import { ProductCard } from "../components/ProductCard";
import { useProducts } from "../api/menu";
import { CATEGORY_LABELS, type Category } from "../lib/menu";

type Filter = "all" | Category;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Всё" },
  { value: "dish", label: CATEGORY_LABELS.dish },
  { value: "drink", label: CATEGORY_LABELS.drink },
  { value: "dessert", label: CATEGORY_LABELS.dessert },
];

export function MenuPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const { data, isLoading, isError, refetch } = useProducts();
  const products = (data ?? []).filter((p) => filter === "all" || p.category === filter);

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <header className="mb-8">
        <p className="text-sm font-medium uppercase tracking-widest text-accent">Меню</p>
        <h1 className="mt-1 text-4xl font-bold sm:text-5xl">Вся кухня</h1>
      </header>

      <div className="sticky top-16 z-30 -mx-4 mb-8 border-b border-border bg-bg/85 px-4 py-3 backdrop-blur-md sm:mx-0 sm:rounded-full sm:border sm:px-2">
        <div className="flex gap-1 overflow-x-auto">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                filter === f.value
                  ? "bg-primary text-primary-contrast"
                  : "text-muted hover:bg-surface-2 hover:text-text"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-80 animate-pulse rounded-2xl border border-border bg-surface-2" />
          ))}
        </div>
      ) : isError ? (
        <div className="py-16 text-center">
          <p className="text-muted">Не удалось загрузить меню.</p>
          <button onClick={() => refetch()} className="mt-3 font-medium text-accent hover:underline">
            Попробовать снова
          </button>
        </div>
      ) : products.length === 0 ? (
        <p className="py-16 text-center text-muted">В этой категории пока пусто.</p>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((product, i) => (
            <ProductCard key={product.id} product={product} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
