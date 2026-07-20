import { useState } from "react";
import { Modal } from "./Modal";
import { Icon } from "./Icon";
import { ProductThumb } from "./ProductThumb";
import { useUI } from "../stores/ui";
import { useToast } from "../stores/toast";
import { useCartQuery, useClearCart, useRemoveItem, useSetItem } from "../api/cart";
import { formatPrice } from "../lib/menu";

type Step = "cart" | "checkout";

export function CartModal() {
  const { data: cart, isLoading } = useCartQuery();
  const setItem = useSetItem();
  const removeItem = useRemoveItem();
  const clearCart = useClearCart();
  const close = useUI((s) => s.closeModal);
  const notify = useToast((s) => s.notify);
  const [step, setStep] = useState<Step>("cart");
  const [payment, setPayment] = useState<"cash" | "card">("cash");

  const items = cart?.items ?? [];
  const total = cart?.total ?? 0;
  const empty = items.length === 0;
  const busy = setItem.isPending || removeItem.isPending;

  function placeOrder(e: React.FormEvent) {
    e.preventDefault();
    notify("Заказ оформлен — ждите звонка");
    clearCart.mutate();
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
        empty || isLoading ? undefined : step === "cart" ? (
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
      {isLoading ? (
        <ul className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <li key={i} className="flex items-center gap-3">
              <div className="h-16 w-16 shrink-0 animate-pulse rounded-xl bg-surface-2" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-2/3 animate-pulse rounded bg-surface-2" />
                <div className="h-3 w-1/4 animate-pulse rounded bg-surface-2" />
              </div>
            </li>
          ))}
        </ul>
      ) : empty ? (
        <div className="flex flex-col items-center py-10 text-center">
          <span className="mb-4 grid h-16 w-16 place-items-center rounded-full bg-surface-2 text-muted">
            <Icon name="cart" size={30} />
          </span>
          <p className="font-medium">Корзина пуста</p>
          <p className="mt-1 text-sm text-muted">Добавьте что-нибудь из меню — мы всё приготовим.</p>
        </div>
      ) : step === "cart" ? (
        <>
          {cart && (cart.removed_items.length > 0 || cart.adjustments.length > 0) && (
            <div className="mb-3 space-y-1.5">
              {cart.removed_items.map((r) => (
                <p
                  key={`r${r.product_id}`}
                  className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger"
                >
                  «{r.name}» {r.reason === "out_of_stock" ? "закончился" : "недоступен"} — удалён из
                  корзины
                </p>
              ))}
              {cart.adjustments.map((a) => (
                <p
                  key={`a${a.product_id}`}
                  className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-400"
                >
                  Количество «{a.name}» уменьшено до {a.to_qty} шт. из-за остатка
                </p>
              ))}
            </div>
          )}
          <ul className="flex flex-col gap-3">
            {items.map((line) => (
              <li key={line.product_id} className="flex items-center gap-3">
                <ProductThumb
                  category={line.category}
                  name={line.name}
                  image={line.image}
                  className="h-16 w-16 shrink-0 rounded-xl"
                  iconSize={26}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{line.name}</p>
                  <p className="tnum text-sm text-muted">{formatPrice(line.price)}</p>
                </div>
                <div className="flex items-center gap-1 rounded-full border border-border p-1">
                  <button
                    onClick={() => setItem.mutate({ productId: line.product_id, quantity: line.quantity - 1 })}
                    disabled={busy}
                    aria-label="Меньше"
                    className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text disabled:opacity-50"
                  >
                    <Icon name="minus" size={15} strokeWidth={2} />
                  </button>
                  <span className="tnum w-6 text-center text-sm font-semibold">{line.quantity}</span>
                  <button
                    onClick={() => setItem.mutate({ productId: line.product_id, quantity: line.quantity + 1 })}
                    disabled={busy}
                    aria-label="Больше"
                    className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text disabled:opacity-50"
                  >
                    <Icon name="plus" size={15} strokeWidth={2} />
                  </button>
                </div>
                <button
                  onClick={() => removeItem.mutate({ productId: line.product_id })}
                  disabled={busy}
                  aria-label={`Убрать ${line.name}`}
                  className="grid h-8 w-8 place-items-center rounded-full text-muted transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-50"
                >
                  <Icon name="trash" size={18} />
                </button>
              </li>
            ))}
          </ul>
        </>
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
