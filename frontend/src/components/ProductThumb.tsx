import { useState } from "react";
import { Icon, CATEGORY_ICON } from "./Icon";
import type { Category } from "../lib/menu";

// shows the product photo; falls back to the category icon if it's missing or fails to load
export function ProductThumb({
  category,
  name,
  image,
  className = "",
  iconSize = 64,
}: {
  category: Category;
  name: string;
  image?: string | null;
  className?: string;
  iconSize?: number;
}) {
  const [failed, setFailed] = useState(false);
  const showImage = Boolean(image) && !failed;

  return (
    <div
      className={`relative flex items-center justify-center overflow-hidden bg-surface-2 ${className}`}
    >
      {showImage ? (
        <img
          src={image ?? undefined}
          alt={name}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <>
          <div
            className="absolute inset-0 opacity-70"
            style={{
              background:
                "radial-gradient(120% 120% at 30% 0%, color-mix(in srgb, var(--accent) 16%, transparent), transparent 60%)",
            }}
          />
          <Icon name={CATEGORY_ICON[category]} size={iconSize} strokeWidth={1.1} className="text-muted/40" />
        </>
      )}
    </div>
  );
}
