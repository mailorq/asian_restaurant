import { Icon } from "../components/Icon";
import { useUI } from "../stores/ui";
import { useAuth } from "../stores/auth";
import { ORDER_STATUS, formatOrderDate, useOrders } from "../api/orders";
import { formatPrice } from "../lib/menu";

export function OrdersPage() {
  const openModal = useUI((s) => s.openModal);
  const navigate = useUI((s) => s.navigate);
  const user = useAuth((s) => s.user);
  const { data: orders, isLoading, isError, refetch } = useOrders(Boolean(user));

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="mb-6 text-3xl font-bold">Мои заказы</h1>

      {!user ? (
        <div className="flex flex-col items-center rounded-2xl border border-border py-14 text-center">
          <span className="mb-4 grid h-14 w-14 place-items-center rounded-full bg-surface-2 text-muted">
            <Icon name="user" size={26} />
          </span>
          <p className="font-medium">Войдите, чтобы видеть заказы</p>
          <button
            onClick={() => openModal("auth", "login")}
            className="mt-4 rounded-full bg-primary px-6 py-2.5 text-sm font-medium text-primary-contrast transition-colors hover:bg-primary-hover"
          >
            Войти
          </button>
        </div>
      ) : isLoading ? (
        <ul className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <li key={i} className="h-28 animate-pulse rounded-2xl bg-surface-2" />
          ))}
        </ul>
      ) : isError ? (
        <div className="rounded-2xl border border-border py-14 text-center">
          <p className="text-sm text-muted">Не удалось загрузить заказы.</p>
          <button onClick={() => refetch()} className="mt-3 font-medium text-accent hover:underline">
            Повторить
          </button>
        </div>
      ) : !orders || orders.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-border py-14 text-center">
          <span className="mb-4 grid h-16 w-16 place-items-center rounded-full bg-surface-2 text-muted">
            <Icon name="clock" size={30} />
          </span>
          <p className="font-medium">Заказов пока нет</p>
          <p className="mt-1 text-sm text-muted">Оформите первый — он появится здесь.</p>
          <button
            onClick={() => navigate({ name: "menu" })}
            className="mt-4 rounded-full bg-primary px-6 py-2.5 text-sm font-medium text-primary-contrast transition-colors hover:bg-primary-hover"
          >
            В меню
          </button>
        </div>
      ) : (
        <ul className="flex flex-col gap-4">
          {orders.map((order) => {
            const status = ORDER_STATUS[order.status];
            return (
              <li key={order.id} className="rounded-2xl border border-border p-5">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">Заказ №{order.id}</span>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${status.cls}`}>
                    {status.label}
                  </span>
                </div>
                <p className="mt-1 flex items-center gap-1.5 text-xs text-muted">
                  <Icon name="clock" size={14} /> {formatOrderDate(order.created_at)}
                </p>
                <ul className="mt-3 flex flex-col gap-1 text-sm">
                  {order.items.map((i) => (
                    <li key={i.product_id} className="flex justify-between text-muted">
                      <span>
                        {i.name}
                        {i.quantity > 1 && <span className="text-muted"> ×{i.quantity}</span>}
                      </span>
                      <span className="tnum">{formatPrice(i.line_total)}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
                  <span className="flex items-center gap-1.5 text-xs text-muted">
                    <Icon name="pin" size={13} /> {order.address}
                  </span>
                  <span className="tnum font-semibold">{formatPrice(order.total)}</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
