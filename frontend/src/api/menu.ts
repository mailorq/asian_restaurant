import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { Category, Product } from "../lib/menu";

export function useProducts(category?: Category) {
  return useQuery({
    queryKey: ["products", category ?? "all"],
    queryFn: () => api<Product[]>(`/menu/products${category ? `?category=${category}` : ""}`),
    staleTime: 60_000,
  });
}

export function useProduct(idOrCode: string | number) {
  return useQuery({
    queryKey: ["product", String(idOrCode)],
    queryFn: () => api<Product>(`/menu/products/${idOrCode}`),
  });
}
