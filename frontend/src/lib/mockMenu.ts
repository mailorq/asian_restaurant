export type Category = "dish" | "drink" | "dessert";

export interface Product {
  id: number;
  name: string;
  category: Category;
  description: string;
  price: number;
  ingredients: string[];
  featured?: boolean;
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

// mock catalog for the layout mockups; real data arrives from the products API later
export const PRODUCTS: Product[] = [
  {
    id: 1,
    name: "Рамен тонкоцу",
    category: "dish",
    description: "Наваристый бульон на свиной кости, пшеничная лапша, чашу и маринованное яйцо.",
    price: 480,
    ingredients: ["Лапша", "Свиной бульон", "Свинина чашу", "Яйцо аджитама", "Зелёный лук"],
    featured: true,
  },
  {
    id: 2,
    name: "Сет суши «Осака»",
    category: "dish",
    description: "Двенадцать роллов с лососем, тунцом и угрём, подаются с имбирём и васаби.",
    price: 690,
    ingredients: ["Рис", "Лосось", "Тунец", "Угорь", "Нори"],
    featured: true,
  },
  {
    id: 3,
    name: "Том ям с креветками",
    category: "dish",
    description: "Кисло-острый тайский суп на кокосовом молоке с королевскими креветками.",
    price: 520,
    ingredients: ["Креветки", "Кокосовое молоко", "Лемонграсс", "Чили", "Лайм"],
    featured: true,
  },
  {
    id: 4,
    name: "Пад тай",
    category: "dish",
    description: "Рисовая лапша вок с креветками, тофу, арахисом и соусом тамаринд.",
    price: 430,
    ingredients: ["Рисовая лапша", "Креветки", "Тофу", "Арахис", "Тамаринд"],
  },
  {
    id: 5,
    name: "Гёдза",
    category: "dish",
    description: "Обжаренные японские пельмени со свининой и капустой, соус понзу.",
    price: 320,
    ingredients: ["Тесто", "Свинина", "Капуста", "Имбирь", "Понзу"],
  },
  {
    id: 6,
    name: "Бибимбап",
    category: "dish",
    description: "Тёплый рис с говядиной, овощами, яйцом и пастой кочудян.",
    price: 460,
    ingredients: ["Рис", "Говядина", "Яйцо", "Шпинат", "Кочудян"],
  },
  {
    id: 7,
    name: "Матча латте",
    category: "drink",
    description: "Церемониальная матча на подогретом молоке, мягкая горчинка и пена.",
    price: 220,
    ingredients: ["Матча", "Молоко"],
    featured: true,
  },
  {
    id: 8,
    name: "Улун молочный",
    category: "drink",
    description: "Полуферментированный чай с кремовым послевкусием, подаётся горячим.",
    price: 180,
    ingredients: ["Чай улун"],
  },
  {
    id: 9,
    name: "Юдзу лимонад",
    category: "drink",
    description: "Освежающий японский цитрус с газом и веточкой мяты.",
    price: 210,
    ingredients: ["Юдзу", "Газированная вода", "Мята"],
  },
  {
    id: 10,
    name: "Имбирный чай",
    category: "drink",
    description: "Свежий имбирь, мёд и лимон — согревающий и ароматный.",
    price: 190,
    ingredients: ["Имбирь", "Мёд", "Лимон"],
  },
  {
    id: 11,
    name: "Моти ассорти",
    category: "dessert",
    description: "Три рисовых пирожных с начинкой из манго, матчи и чёрного кунжута.",
    price: 260,
    ingredients: ["Клейкий рис", "Манго", "Матча", "Кунжут"],
    featured: true,
  },
  {
    id: 12,
    name: "Манго-пудинг",
    category: "dessert",
    description: "Нежный пудинг на кокосовом молоке со свежим манго и чиа.",
    price: 240,
    ingredients: ["Манго", "Кокосовое молоко", "Чиа"],
  },
  {
    id: 13,
    name: "Тайяки",
    category: "dessert",
    description: "Вафля в форме рыбки с начинкой из красной фасоли анко.",
    price: 200,
    ingredients: ["Тесто", "Паста анко", "Мёд"],
  },
  {
    id: 14,
    name: "Чизкейк матча",
    category: "dessert",
    description: "Воздушный чизкейк с зелёным чаем и хрустящей основой.",
    price: 280,
    ingredients: ["Сливочный сыр", "Матча", "Печенье"],
  },
];

export const getProduct = (id: number): Product | undefined =>
  PRODUCTS.find((p) => p.id === id);

export const byCategory = (category: Category): Product[] =>
  PRODUCTS.filter((p) => p.category === category);

export const featured = (): Product[] => PRODUCTS.filter((p) => p.featured);

export const formatPrice = (value: number): string => `${value} ₽`;
