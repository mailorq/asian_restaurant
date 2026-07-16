import { useMemo, useState } from "react";
import { Modal } from "./Modal";
import { Icon } from "./Icon";
import { ProductThumb } from "./ProductThumb";
import { useCart } from "../stores/cart";
import { useUI } from "../stores/ui";
import { useToast } from "../stores/toast";
import { getProduct, formatPrice } from "../lib/mockMenu";

type Step = "cart" | "checkout";

export function CartModal() {
  const lines = useCart((s) => s.lines);
  const setQuantity = useCart((s) => s.setQuantity);
  const remove = useCart((s) => s.remove);
  const clear = useCart((s) => s.clear);
  const close = useUI((s) => s.closeModal);
  const notify = useToast((s) => s.notify);
  const [step, setStep] = useState<Step>("cart");
  const [payment, setPayment] = useState<"cash" | "card">("cash");

  const items = useMemo(
    () =>
      lines
        .map((l) => ({ product: getProduct(l.productId), quantity: l.quantity }))
        .filter((i): i is { product: NonNullable<ReturnType<typeof getProduct>>; quantity: number } =>
          Boolean(i.product),
        ),
    [lines],
  );

  const total = items.reduce((sum, i) => sum + i.product.price * i.quantity, 0);
  const empty = items.length === 0;

  function placeOrder(e: React.FormEvent) {
    e.preventDefault();
    notify("Заказ оформлен — ждите звонка");
    clear();
    close();
  }

  const title =
    step === "cart" ? "Корзина" : (
      <button onClick={() => setStep("cart")} className="flex items-center gap-2 hover:text-accent">
        <Icon name="arrowLeft" size={20} /> Оформление
      </button>
    );

  return (
    <Modal
      title={title}
      onClose={close}
      footer={
        empty ? undefined : step === "cart" ? (
          <div>
            <div className="mb-3 flex items-center justify-between">
              <span className="text-muted">Итого</span>
              <span className="tnum text-xl font-semibold">{formatPrice(total)}</span>
            </div>
            <button
              onClick={() => setStep("checkout")}
              className="h-12 w-full rounded-xl bg-primary font-medium text-primary-contrast transition-[background-color,transform] duration-200 hover:bg-primary-hover active:scale-[0.99]"
            >
              Оформить заказ
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-muted">К оплате</span>
            <span className="tnum text-xl font-semibold">{formatPrice(total)}</span>
          </div>
        )
      }
    >
      {empty ? (
        <div className="flex flex-col items-center py-10 text-center">
          <span className="mb-4 grid h-16 w-16 place-items-center rounded-full bg-surface-2 text-muted">
            <Icon name="cart" size={30} />
          </span>
          <p className="font-medium">Корзина пуста</p>
          <p className="mt-1 text-sm text-muted">Добавьте что-нибудь из меню — мы всё приготовим.</p>
        </div>
      ) : step === "cart" ? (
        <ul className="flex flex-col gap-3">
          {items.map(({ product, quantity }) => (
            <li key={product.id} className="flex items-center gap-3">
              <ProductThumb
                category={product.category}
                name={product.name}
                image={product.image}
                className="h-16 w-16 shrink-0 rounded-xl"
                iconSize={26}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{product.name}</p>
                <p className="tnum text-sm text-muted">{formatPrice(product.price)}</p>
              </div>
              <div className="flex items-center gap-1 rounded-full border border-border p-1">
                <button
                  onClick={() => setQuantity(product.id, quantity - 1)}
                  aria-label="Меньше"
                  className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text"
                >
                  <Icon name="minus" size={15} strokeWidth={2} />
                </button>
                <span className="tnum w-6 text-center text-sm font-semibold">{quantity}</span>
                <button
                  onClick={() => setQuantity(product.id, quantity + 1)}
                  aria-label="Больше"
                  className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text"
                >
                  <Icon name="plus" size={15} strokeWidth={2} />
                </button>
              </div>
              <button
                onClick={() => remove(product.id)}
                aria-label={`Убрать ${product.name}`}
                className="grid h-8 w-8 place-items-center rounded-full text-muted transition-colors hover:bg-danger/10 hover:text-danger"
              >
                <Icon name="trash" size={18} />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <form id="checkout-form" onSubmit={placeOrder} className="flex flex-col gap-4">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-muted">Имя<span className="text-accent"> *</span></span>
            <input
              required
              placeholder="Иван"
              className="h-11 w-full rounded-xl border border-border bg-surface-2 px-3.5 focus:border-primary focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-muted">Телефон<span className="text-accent"> *</span></span>
            <input
              required
              type="tel"
              placeholder="+7 900 000-00-00"
              className="h-11 w-full rounded-xl border border-border bg-surface-2 px-3.5 focus:border-primary focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-muted">Адрес доставки<span className="text-accent"> *</span></span>
            <input
              required
              placeholder="ул. Пушкина, 12, кв. 3"
              className="h-11 w-full rounded-xl border border-border bg-surface-2 px-3.5 focus:border-primary focus:outline-none"
            />
          </label>

          <fieldset>
            <span className="mb-1.5 block text-sm font-medium text-muted">Оплата</span>
            <div className="grid grid-cols-2 gap-3">
              {([
                { v: "cash", label: "Наличными" },
                { v: "card", label: "Картой" },
              ] as const).map((opt) => (
                <label
                  key={opt.v}
                  className={`cursor-pointer rounded-xl border-2 px-4 py-3 text-center text-sm font-medium transition-colors ${
                    payment === opt.v
                      ? "border-accent bg-accent/10 text-text"
                      : "border-border text-muted hover:border-accent/50"
                  }`}
                >
                  <input
                    type="radio"
                    name="payment"
                    value={opt.v}
                    checked={payment === opt.v}
                    onChange={() => setPayment(opt.v)}
                    className="sr-only"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </fieldset>

          <button
            type="submit"
            className="mt-1 h-12 rounded-xl bg-primary font-medium text-primary-contrast transition-[background-color,transform] duration-200 hover:bg-primary-hover active:scale-[0.99]"
          >
            Подтвердить заказ
          </button>
        </form>
      )}
    </Modal>
  );
}
