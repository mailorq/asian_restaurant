import { useState } from "react";
import { ProductThumb } from "../components/ProductThumb";
import { ProductCard } from "../components/ProductCard";
import { Icon } from "../components/Icon";
import { useCart } from "../stores/cart";
import { useUI } from "../stores/ui";
import { useToast } from "../stores/toast";
import { getProduct, byCategory, CATEGORY_LABEL_ONE, formatPrice } from "../lib/mockMenu";

export function ProductPage({ id }: { id: number }) {
  const product = getProduct(id);
  const add = useCart((s) => s.add);
  const navigate = useUI((s) => s.navigate);
  const notify = useToast((s) => s.notify);
  const [qty, setQty] = useState(1);

  if (!product) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-24 text-center sm:px-6">
        <p className="text-lg font-medium">Позиция не найдена</p>
        <button onClick={() => navigate({ name: "menu" })} className="mt-4 text-accent hover:underline">
          Вернуться в меню
        </button>
      </div>
    );
  }

  const related = byCategory(product.category).filter((p) => p.id !== product.id).slice(0, 3);

  function addToCart() {
    for (let i = 0; i < qty; i++) add(product!.id);
    notify(`${product!.name} × ${qty} — в корзине`);
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
          <span className="mb-3 w-fit rounded-full bg-surface-2 px-3 py-1 text-xs font-medium text-muted">
            {CATEGORY_LABEL_ONE[product.category]}
          </span>
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

          <div className="mt-8 flex items-center gap-4">
            <div className="flex items-center gap-1 rounded-full border border-border p-1.5">
              <button
                onClick={() => setQty((q) => Math.max(1, q - 1))}
                aria-label="Меньше"
                className="grid h-9 w-9 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text"
              >
                <Icon name="minus" size={17} strokeWidth={2} />
              </button>
              <span className="tnum w-8 text-center font-semibold">{qty}</span>
              <button
                onClick={() => setQty((q) => q + 1)}
                aria-label="Больше"
                className="grid h-9 w-9 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text"
              >
                <Icon name="plus" size={17} strokeWidth={2} />
              </button>
            </div>
            <button
              onClick={addToCart}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-primary px-7 py-3.5 font-medium text-primary-contrast transition-[background-color,transform] duration-200 hover:bg-primary-hover active:scale-[0.98]"
            >
              <Icon name="cart" size={19} /> В корзину · {formatPrice(product.price * qty)}
            </button>
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
