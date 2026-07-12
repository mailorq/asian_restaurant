import { create } from "zustand";
import { persist } from "zustand/middleware";

// holds only product id + quantity; price and totals are computed server-side
export interface CartLine {
  productId: number;
  quantity: number;
}

interface CartState {
  lines: CartLine[];
  add: (productId: number) => void;
  setQuantity: (productId: number, quantity: number) => void;
  remove: (productId: number) => void;
  clear: () => void;
}

export const useCart = create<CartState>()(
  persist(
    (set) => ({
      lines: [],
      add: (productId) =>
        set((s) => {
          const line = s.lines.find((l) => l.productId === productId);
          return line
            ? {
                lines: s.lines.map((l) =>
                  l.productId === productId ? { ...l, quantity: l.quantity + 1 } : l,
                ),
              }
            : { lines: [...s.lines, { productId, quantity: 1 }] };
        }),
      setQuantity: (productId, quantity) =>
        set((s) => ({
          lines:
            quantity <= 0
              ? s.lines.filter((l) => l.productId !== productId)
              : s.lines.map((l) => (l.productId === productId ? { ...l, quantity } : l)),
        })),
      remove: (productId) =>
        set((s) => ({ lines: s.lines.filter((l) => l.productId !== productId) })),
      clear: () => set({ lines: [] }),
    }),
    { name: "cart" },
  ),
);
