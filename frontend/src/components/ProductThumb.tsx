import { Icon, CATEGORY_ICON } from "./Icon";
import type { Category } from "../lib/mockMenu";

// editorial placeholder used until real product photos are served from /media
export function ProductThumb({
  category,
  name,
  className = "",
  iconSize = 64,
}: {
  category: Category;
  name: string;
  className?: string;
  iconSize?: number;
}) {
  return (
    <div
      className={`relative flex items-center justify-center overflow-hidden bg-surface-2 ${className}`}
      role="img"
      aria-label={name}
    >
      <div
        className="absolute inset-0 opacity-70"
        style={{
          background:
            "radial-gradient(120% 120% at 30% 0%, color-mix(in srgb, var(--accent) 16%, transparent), transparent 60%)",
        }}
      />
      <Icon name={CATEGORY_ICON[category]} size={iconSize} strokeWidth={1.1} className="text-muted/40" />
    </div>
  );
}
