import { ProductThumb } from "./ProductThumb";
import { Icon } from "./Icon";
import { useAddItem } from "../api/cart";
import { useToast } from "../stores/toast";
import { useUI } from "../stores/ui";
import { CATEGORY_LABEL_ONE, formatPrice, type Product } from "../lib/menu";

export function ProductCard({ product, index = 0 }: { product: Product; index?: number }) {
  const addItem = useAddItem();
  const notify = useToast((s) => s.notify);
  const navigate = useUI((s) => s.navigate);

  function open() {
    navigate({ name: "product", id: product.id });
  }

  function addToCart(e: React.MouseEvent) {
    e.stopPropagation();
    if (!product.available || addItem.isPending) return;
    addItem.mutate(
      { productId: product.id },
      { onSuccess: () => notify(`${product.name} — добавлено в корзину`) },
    );
  }

  return (
    <article
      onClick={open}
      className="group anim-fade-up flex cursor-pointer flex-col overflow-hidden rounded-2xl border border-border bg-surface transition-[transform,box-shadow] duration-300 hover:-translate-y-1 hover:shadow-[0_18px_40px_-24px_rgba(0,0,0,0.45)]"
      style={{ animationDelay: `${Math.min(index, 8) * 45}ms` }}
    >
      <div className="relative overflow-hidden">
        <ProductThumb
          category={product.category}
          name={product.name}
          image={product.image}
          className={`aspect-[4/3] transition-transform duration-500 group-hover:scale-[1.04] ${
            product.available ? "" : "opacity-60"
          }`}
        />
        <span className="absolute left-3 top-3 rounded-full bg-surface/85 px-3 py-1 text-xs font-medium text-muted backdrop-blur-sm">
          {CATEGORY_LABEL_ONE[product.category]}
        </span>
        {!product.available && (
          <span className="absolute right-3 top-3 rounded-full bg-danger/90 px-3 py-1 text-xs font-medium text-white">
            Нет в наличии
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col p-5">
        <h3 className="text-lg font-semibold leading-snug">{product.name}</h3>
        <p className="mt-1.5 line-clamp-2 text-sm text-muted">{product.description}</p>

        <div className="mt-4 flex items-center justify-between pt-1">
          <span className="tnum text-lg font-semibold">{formatPrice(product.price)}</span>
          {product.available ? (
            <button
              onClick={addToCart}
              disabled={addItem.isPending}
              aria-label={`Добавить «${product.name}» в корзину`}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-contrast transition-[background-color,transform] duration-200 hover:bg-primary-hover active:scale-95 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-60"
            >
              <Icon name="plus" size={16} strokeWidth={2} />
              В корзину
            </button>
          ) : (
            <span className="rounded-full bg-surface-2 px-3.5 py-2 text-sm font-medium text-muted">
              Нет в наличии
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
