import { useMemo, useRef, useState } from "react";
import { Icon } from "./Icon";
import { ProductThumb } from "./ProductThumb";
import { useUI } from "../stores/ui";
import { PRODUCTS, CATEGORY_LABEL_ONE, formatPrice } from "../lib/mockMenu";

export function SearchBox() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const navigate = useUI((s) => s.navigate);
  const boxRef = useRef<HTMLDivElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return PRODUCTS.filter((p) => p.name.toLowerCase().includes(q)).slice(0, 5);
  }, [query]);

  function pick(id: number) {
    setQuery("");
    setOpen(false);
    navigate({ name: "product", id });
  }

  return (
    <div ref={boxRef} className="relative w-full max-w-xs">
      <Icon
        name="search"
        size={18}
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
      />
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        placeholder="Поиск по меню"
        className="h-10 w-full rounded-full border border-border bg-surface-2 pl-9 pr-4 text-sm text-text placeholder:text-muted focus:border-primary focus:outline-none"
      />

      {open && results.length > 0 && (
        <div className="anim-fade-up absolute left-0 right-0 top-12 z-50 overflow-hidden rounded-2xl border border-border bg-surface shadow-xl">
          {results.map((p) => (
            <button
              key={p.id}
              onMouseDown={() => pick(p.id)}
              className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-surface-2"
            >
              <ProductThumb category={p.category} name={p.name} className="h-11 w-11 shrink-0 rounded-lg" iconSize={22} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{p.name}</span>
                <span className="block text-xs text-muted">{CATEGORY_LABEL_ONE[p.category]}</span>
              </span>
              <span className="tnum text-sm font-semibold text-accent">{formatPrice(p.price)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
