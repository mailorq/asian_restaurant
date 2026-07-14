import { ProductCard } from "../components/ProductCard";
import { Icon, CATEGORY_ICON } from "../components/Icon";
import { useUI } from "../stores/ui";
import { featured, CATEGORY_LABELS, byCategory, type Category } from "../lib/mockMenu";
import { plural } from "../lib/format";

const PERKS = [
  { icon: "star", title: "Свежие продукты", text: "Готовим из сезонных ингредиентов каждый день." },
  { icon: "clock", title: "Доставка 60 минут", text: "Привезём горячим по всему городу." },
  { icon: "cart", title: "Удобная оплата", text: "Картой онлайн или наличными курьеру." },
];

const CATEGORIES: Category[] = ["dish", "drink", "dessert"];

export function HomePage() {
  const navigate = useUI((s) => s.navigate);

  return (
    <div>
      <section className="relative overflow-hidden border-b border-border">
        <div className="mx-auto max-w-6xl px-4 py-20 text-center sm:px-6 sm:py-28">
          <p className="anim-fade-up mb-5 inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-1.5 text-xs font-medium uppercase tracking-widest text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" /> Азиатская кухня · доставка
          </p>
          <h1
            className="anim-fade-up mx-auto max-w-3xl text-balance text-5xl font-bold leading-[1.05] sm:text-7xl"
            style={{ animationDelay: "60ms" }}
          >
            Вкус Азии <span className="text-accent">у вас дома</span>
          </h1>
          <p
            className="anim-fade-up mx-auto mt-6 max-w-xl text-lg text-muted"
            style={{ animationDelay: "120ms" }}
          >
            Рамен, суши, вок и десерты от шефа. Собрали лучшее из Японии, Кореи, Таиланда и Китая —
            в одном меню.
          </p>
          <div
            className="anim-fade-up mt-9 flex flex-wrap items-center justify-center gap-3"
            style={{ animationDelay: "180ms" }}
          >
            <button
              onClick={() => navigate({ name: "menu" })}
              className="inline-flex items-center gap-2 rounded-full bg-primary px-7 py-3.5 font-medium text-primary-contrast transition-[background-color,transform] duration-200 hover:bg-primary-hover active:scale-[0.98]"
            >
              Смотреть меню <Icon name="arrowRight" size={18} strokeWidth={2} />
            </button>
            <a
              href="#popular"
              className="rounded-full border border-border px-7 py-3.5 font-medium transition-colors hover:border-accent hover:text-accent"
            >
              Популярное
            </a>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="grid gap-6 sm:grid-cols-3">
          {PERKS.map((p) => (
            <div key={p.title} className="flex gap-4">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-surface-2 text-accent">
                <Icon name={p.icon} size={20} />
              </span>
              <div>
                <p className="font-semibold">{p.title}</p>
                <p className="mt-0.5 text-sm text-muted">{p.text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section id="popular" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-8 sm:px-6">
        <div className="mb-8 flex items-end justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-widest text-accent">Хиты меню</p>
            <h2 className="mt-1 text-3xl font-bold sm:text-4xl">Популярное</h2>
          </div>
          <button
            onClick={() => navigate({ name: "menu" })}
            className="hidden items-center gap-1.5 text-sm font-medium text-muted transition-colors hover:text-text sm:flex"
          >
            Всё меню <Icon name="arrowRight" size={16} />
          </button>
        </div>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {featured().map((product, i) => (
            <ProductCard key={product.id} product={product} index={i} />
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="grid gap-4 sm:grid-cols-3">
          {CATEGORIES.map((cat) => {
            const count = byCategory(cat).length;
            return (
              <button
                key={cat}
                onClick={() => navigate({ name: "menu" })}
                className="group relative flex h-44 flex-col justify-end overflow-hidden rounded-2xl border border-border bg-surface p-6 text-left transition-[transform,border-color,box-shadow] duration-300 hover:-translate-y-1 hover:border-accent/40 hover:shadow-lg"
              >
                <Icon
                  name={CATEGORY_ICON[cat]}
                  size={132}
                  strokeWidth={0.9}
                  className="pointer-events-none absolute -right-5 -top-4 text-accent/15 transition-transform duration-500 group-hover:-rotate-6 group-hover:scale-110"
                />
                <p className="relative font-display text-2xl font-bold">{CATEGORY_LABELS[cat]}</p>
                <p className="relative mt-0.5 text-sm text-muted">
                  {count} {plural(count, ["позиция", "позиции", "позиций"])}
                </p>
                <span className="relative mt-3 inline-flex items-center gap-1 text-sm font-medium text-accent">
                  Смотреть меню <Icon name="arrowRight" size={15} />
                </span>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
