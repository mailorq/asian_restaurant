import { useState } from "react";
import { ProductThumb } from "../components/ProductThumb";
import { ProductCard } from "../components/ProductCard";
import { Icon } from "../components/Icon";
import { useUI } from "../stores/ui";
import { useToast } from "../stores/toast";
import { useProduct, useProducts } from "../api/menu";
import { useAddItem } from "../api/cart";
import { CATEGORY_LABEL_ONE, formatPrice } from "../lib/menu";

export function ProductPage({ id }: { id: number }) {
  const { data: product, isLoading, isError } = useProduct(id);
  const { data: all } = useProducts();
  const addItem = useAddItem();
  const navigate = useUI((s) => s.navigate);
  const notify = useToast((s) => s.notify);
  const [qty, setQty] = useState(1);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="grid gap-10 lg:grid-cols-2">
          <div className="aspect-square animate-pulse rounded-3xl bg-surface-2" />
          <div className="space-y-4">
            <div className="h-10 w-2/3 animate-pulse rounded bg-surface-2" />
            <div className="h-8 w-1/3 animate-pulse rounded bg-surface-2" />
            <div className="h-24 animate-pulse rounded bg-surface-2" />
          </div>
        </div>
      </div>
    );
  }

  if (isError || !product) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-24 text-center sm:px-6">
        <p className="text-lg font-medium">Позиция не найдена</p>
        <button onClick={() => navigate({ name: "menu" })} className="mt-4 text-accent hover:underline">
          Вернуться в меню
        </button>
      </div>
    );
  }

  const related = (all ?? [])
    .filter((p) => p.category === product.category && p.id !== product.id)
    .slice(0, 3);
  const maxQty = Math.max(1, product.stock);
  const qtyCapped = Math.min(qty, maxQty);

  function addToCart() {
    if (!product!.available || addItem.isPending) return;
    addItem.mutate(
      { productId: product!.id, quantity: qtyCapped },
      { onSuccess: () => notify(`${product!.name} × ${qtyCapped} — в корзине`) },
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <button
        onClick={() => navigate({ name: "menu" })}
        className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-muted transition-colors hover:text-text"
      >
        <Icon name="arrowLeft" size={18} /> Назад в меню
      </button>

      <div className="grid gap-10 lg:grid-cols-2">
        <ProductThumb
          category={product.category}
          name={product.name}
          image={product.image}
          className="anim-scale-in aspect-square rounded-3xl border border-border"
          iconSize={120}
        />

        <div className="anim-fade-up flex flex-col">
          <div className="mb-3 flex items-center gap-2">
            <span className="w-fit rounded-full bg-surface-2 px-3 py-1 text-xs font-medium text-muted">
              {CATEGORY_LABEL_ONE[product.category]}
            </span>
            {!product.available && (
              <span className="rounded-full bg-danger/15 px-3 py-1 text-xs font-medium text-danger">
                Нет в наличии
              </span>
            )}
          </div>
          <h1 className="text-4xl font-bold leading-tight sm:text-5xl">{product.name}</h1>
          <p className="tnum mt-4 text-3xl font-semibold text-accent">{formatPrice(product.price)}</p>
          <p className="mt-5 text-lg leading-relaxed text-muted">{product.description}</p>

          <div className="mt-7">
            <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Состав</p>
            <div className="flex flex-wrap gap-2">
              {product.ingredients.map((ing) => (
                <span key={ing} className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-sm">
                  {ing}
                </span>
              ))}
            </div>
          </div>

          {product.allergens.length > 0 && (
            <p className="mt-4 text-sm text-muted">
              <span className="font-medium">Аллергены:</span> {product.allergens.join(", ")}
            </p>
          )}

          <div className="mt-8 flex items-center gap-4">
            <div className="flex items-center gap-1 rounded-full border border-border p-1.5">
              <button
                onClick={() => setQty((q) => Math.max(1, q - 1))}
                aria-label="Меньше"
                className="grid h-9 w-9 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text"
              >
                <Icon name="minus" size={17} strokeWidth={2} />
              </button>
              <span className="tnum w-8 text-center font-semibold">{qtyCapped}</span>
              <button
                onClick={() => setQty((q) => Math.min(maxQty, q + 1))}
                aria-label="Больше"
                className="grid h-9 w-9 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text disabled:opacity-40"
                disabled={qtyCapped >= maxQty}
              >
                <Icon name="plus" size={17} strokeWidth={2} />
              </button>
            </div>
            {product.available ? (
              <button
                onClick={addToCart}
                disabled={addItem.isPending}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-primary px-7 py-3.5 font-medium text-primary-contrast transition-[background-color,transform] duration-200 hover:bg-primary-hover active:scale-[0.98] disabled:opacity-60"
              >
                <Icon name="cart" size={19} /> В корзину · {formatPrice(product.price * qtyCapped)}
              </button>
            ) : (
              <span className="flex-1 rounded-full bg-surface-2 px-7 py-3.5 text-center font-medium text-muted">
                Нет в наличии
              </span>
            )}
          </div>
        </div>
      </div>

      {related.length > 0 && (
        <section className="mt-20">
          <h2 className="mb-6 text-2xl font-bold">Похожие позиции</h2>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {related.map((p, i) => (
              <ProductCard key={p.id} product={p} index={i} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
