import { Icon } from "./Icon";
import { strings } from "../lib/i18n";
import { CATEGORY_LABELS } from "../lib/mockMenu";

export function Footer() {
  const f = strings.footer;

  return (
    <footer className="mt-24 border-t border-border bg-surface">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:px-6 md:grid-cols-3">
        <div>
          <p className="font-display text-xl font-bold">
            Asian<span className="text-accent">.</span>
          </p>
          <p className="mt-3 max-w-xs text-sm text-muted">{f.tagline}</p>
        </div>

        <div className="text-sm">
          <p className="mb-3 font-semibold">{f.contactsTitle}</p>
          <p className="flex items-center gap-2 text-muted">
            <Icon name="pin" size={16} /> {f.address}
          </p>
          <p className="mt-2 flex items-center gap-2 text-muted">
            <Icon name="phone" size={16} /> {f.phone}
          </p>
          <p className="mt-2 flex items-center gap-2 text-muted">
            <Icon name="clock" size={16} /> {f.hours}
          </p>
        </div>

        <div className="text-sm">
          <p className="mb-3 font-semibold">{f.menuTitle}</p>
          <p className="text-muted">{CATEGORY_LABELS.dish}</p>
          <p className="mt-2 text-muted">{CATEGORY_LABELS.drink}</p>
          <p className="mt-2 text-muted">{CATEGORY_LABELS.dessert}</p>
        </div>
      </div>

      <div className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-5 text-xs text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>{f.rights}</p>
          <p>
            {f.createdBy}{" "}
            <a
              href="https://mailorq.com"
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-accent hover:underline"
            >
              mailorq
            </a>
          </p>
        </div>
      </div>
    </footer>
  );
}
