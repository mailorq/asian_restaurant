export type Category = "dish" | "drink" | "dessert";

export interface Product {
  id: number;
  code: string;
  category: Category;
  name: string;
  description: string;
  price: number;
  image: string | null;
  ingredients: string[];
  allergens: string[];
  is_featured: boolean;
  available: boolean;
  stock: number;
}

export const CATEGORY_LABELS: Record<Category, string> = {
  dish: "Блюда",
  drink: "Напитки",
  dessert: "Десерты",
};

export const CATEGORY_LABEL_ONE: Record<Category, string> = {
  dish: "Блюдо",
  drink: "Напиток",
  dessert: "Десерт",
};

export const formatPrice = (value: number): string => `${value} ₴`;
