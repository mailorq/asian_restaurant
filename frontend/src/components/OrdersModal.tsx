import { Modal } from "./Modal";
import { Icon } from "./Icon";
import { useUI } from "../stores/ui";
import { formatPrice } from "../lib/menu";

type Status = "pending" | "delivered" | "cancelled";

const STATUS: Record<Status, { label: string; cls: string }> = {
  pending: { label: "Готовится", cls: "bg-accent/15 text-accent" },
  delivered: { label: "Доставлен", cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" },
  cancelled: { label: "Отменён", cls: "bg-danger/15 text-danger" },
};

const MOCK_ORDERS: { id: number; date: string; items: string; total: number; status: Status }[] = [
  { id: 1043, date: "14 июля, 19:20", items: "Рамен тонцоцу, Гёдза, Матча латте", total: 1020, status: "pending" },
  { id: 1039, date: "10 июля, 13:05", items: "Сет суши «Осака», Юдзу лимонад", total: 900, status: "delivered" },
  { id: 1021, date: "2 июля, 20:41", items: "Том ям с креветками, Моти ассорти", total: 780, status: "delivered" },
];

export function OrdersModal() {
  const close = useUI((s) => s.closeModal);

  return (
    <Modal title="Мои заказы" onClose={close}>
      <ul className="flex flex-col gap-3">
        {MOCK_ORDERS.map((o) => (
          <li key={o.id} className="rounded-2xl border border-border p-4">
            <div className="flex items-center justify-between">
              <span className="font-semibold">Заказ №{o.id}</span>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS[o.status].cls}`}>
                {STATUS[o.status].label}
              </span>
            </div>
            <p className="mt-1 flex items-center gap-1.5 text-xs text-muted">
              <Icon name="clock" size={14} /> {o.date}
            </p>
            <p className="mt-2 text-sm text-muted">{o.items}</p>
            <p className="tnum mt-2 text-right font-semibold">{formatPrice(o.total)}</p>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
