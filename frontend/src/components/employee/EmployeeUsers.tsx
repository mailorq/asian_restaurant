import { useState } from "react";
import { Modal } from "../Modal";
import { Icon } from "../Icon";
import { useToast } from "../../stores/toast";
import { useAuth } from "../../stores/auth";
import {
  useEmployeeUsers,
  useSetRole,
  useUserDetail,
  type EmployeeUser,
} from "../../api/employee";
import { ORDER_STATUS, formatOrderDate } from "../../api/orders";
import { formatPrice } from "../../lib/menu";
import { formatUaPhone } from "../../lib/phone";

function UserDetailModal({ userId, onClose }: { userId: number; onClose: () => void }) {
  const { data, isLoading } = useUserDetail(userId);
  return (
    <Modal title={data ? data.name || data.username : "Пользователь"} onClose={onClose}>
      {isLoading || !data ? (
        <div className="h-40 animate-pulse rounded-xl bg-surface-2" />
      ) : (
        <div>
          <p className="tnum text-sm text-muted">
            {data.phone ? formatUaPhone(data.phone) : "Телефон не указан"}
          </p>
          <p className="mb-3 mt-4 text-sm font-semibold uppercase tracking-wide text-muted">
            Заказы ({data.orders.length})
          </p>
          {data.orders.length === 0 ? (
            <p className="text-sm text-muted">Заказов нет</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {data.orders.map((o) => (
                <li key={o.id} className="rounded-xl border border-border p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Заказ №{o.id}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ORDER_STATUS[o.status].cls}`}>
                      {ORDER_STATUS[o.status].label}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted">{formatOrderDate(o.created_at)}</p>
                  <p className="tnum mt-1 text-right text-sm font-semibold">{formatPrice(o.total)}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
}

export function EmployeeUsers() {
  const me = useAuth((s) => s.user);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [detailId, setDetailId] = useState<number | null>(null);
  const { data, isLoading, isError, refetch } = useEmployeeUsers(search, page);
  const setRole = useSetRole();
  const notify = useToast((s) => s.notify);

  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  function onSearch(value: string) {
    setSearch(value);
    setPage(1);
  }

  function toggleRole(u: EmployeeUser) {
    setRole.mutate(
      { userId: u.id, grant: !u.is_employee },
      {
        onSuccess: () =>
          notify(u.is_employee ? `Роль отозвана: ${u.name || u.username}` : `Роль выдана: ${u.name || u.username}`),
        onError: (e) => notify(e instanceof Error ? e.message : "Не удалось изменить роль", "error"),
      },
    );
  }

  return (
    <div>
      <div className="mb-5 flex items-center gap-2 rounded-xl border border-border bg-surface-2 px-3.5">
        <Icon name="search" size={18} className="text-muted" />
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Поиск по имени или телефону"
          className="h-11 w-full bg-transparent focus:outline-none"
        />
      </div>

      {isLoading ? (
        <ul className="flex flex-col gap-3">
          {[0, 1, 2, 3].map((i) => (
            <li key={i} className="h-16 animate-pulse rounded-2xl bg-surface-2" />
          ))}
        </ul>
      ) : isError ? (
        <div className="rounded-2xl border border-border py-12 text-center">
          <p className="text-sm text-muted">Не удалось загрузить пользователей.</p>
          <button onClick={() => refetch()} className="mt-3 font-medium text-accent hover:underline">
            Повторить
          </button>
        </div>
      ) : !data || data.items.length === 0 ? (
        <p className="rounded-2xl border border-border py-12 text-center text-sm text-muted">
          Никого не найдено
        </p>
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {data.items.map((u) => (
              <li
                key={u.id}
                className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-border p-4"
              >
                <button
                  onClick={() => setDetailId(u.id)}
                  className="min-w-0 flex-1 text-left"
                >
                  <p className="truncate font-medium">
                    {u.name || u.username}
                    {u.is_employee && (
                      <span className="ml-2 rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium text-accent">
                        сотрудник
                      </span>
                    )}
                  </p>
                  <p className="tnum text-xs text-muted">
                    {u.phone ? formatUaPhone(u.phone) : u.username}
                  </p>
                </button>
                <span className="text-xs text-muted">
                  активных заказов: <span className="tnum font-semibold text-text">{u.active_orders_count}</span>
                </span>
                {me?.is_superuser && (
                  <button
                    onClick={() => toggleRole(u)}
                    disabled={setRole.isPending}
                    className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                      u.is_employee
                        ? "border border-danger/40 text-danger hover:bg-danger/10"
                        : "border border-border text-muted hover:border-accent hover:text-accent"
                    }`}
                  >
                    {u.is_employee ? "Отозвать роль" : "Выдать роль"}
                  </button>
                )}
              </li>
            ))}
          </ul>

          <div className="mt-5 flex items-center justify-between text-sm text-muted">
            <span>Всего: {total}</span>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="grid h-9 w-9 place-items-center rounded-full border border-border hover:text-text disabled:opacity-40"
                aria-label="Назад"
              >
                <Icon name="arrowLeft" size={16} />
              </button>
              <span className="tnum">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="grid h-9 w-9 place-items-center rounded-full border border-border hover:text-text disabled:opacity-40"
                aria-label="Вперёд"
              >
                <Icon name="arrowRight" size={16} />
              </button>
            </div>
          </div>
        </>
      )}

      {detailId !== null && <UserDetailModal userId={detailId} onClose={() => setDetailId(null)} />}
    </div>
  );
}
