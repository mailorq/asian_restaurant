export type Category = "dish" | "drink" | "dessert";

export interface Product {
  id: number;
  name: string;
  category: Category;
  description: string;
  price: number;
  ingredients: string[];
  image: string;
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

const image = (category: Category, number: number) =>
  `/assets/menu-optimized/${category}_${number}.webp`;

export const PRODUCTS: Product[] = [
  {
    id: 1,
    name: "Рамен тонкоцу",
    category: "dish",
    description: "Насыщенный японский бульон со свининой чашу, лапшой и маринованным яйцом.",
    price: 480,
    ingredients: ["Лапша", "Свиная грудинка", "Яйцо аджитама", "Нори", "Зелёный лук"],
    image: image("dish", 1),
    featured: true,
  },
  {
    id: 2,
    name: "Сет «Осака»",
    category: "dish",
    description: "12 роллов с лососем, тунцом, угрём, авокадо и огурцом.",
    price: 690,
    ingredients: ["Рис", "Лосось", "Тунец", "Угорь", "Нори"],
    image: image("dish", 2),
    featured: true,
  },
  {
    id: 3,
    name: "Сет «Дракон»",
    category: "dish",
    description: "12 роллов с угрём, лососем и авокадо под соусом унаги.",
    price: 720,
    ingredients: ["Рис", "Угорь", "Лосось", "Авокадо", "Соус унаги"],
    image: image("dish", 3),
  },
  {
    id: 4,
    name: "Том ям с креветками",
    category: "dish",
    description: "Тайский остро-кислый суп на кокосовой основе с королевскими креветками.",
    price: 520,
    ingredients: ["Креветки", "Кокосовое молоко", "Грибы", "Лемонграсс", "Лайм"],
    image: image("dish", 4),
    featured: true,
  },
  {
    id: 5,
    name: "Пад тай с креветками",
    category: "dish",
    description: "Рисовая лапша вок с креветками, тофу, арахисом и соусом тамаринд.",
    price: 430,
    ingredients: ["Рисовая лапша", "Креветки", "Тофу", "Арахис", "Тамаринд"],
    image: image("dish", 5),
  },
  {
    id: 6,
    name: "Гёдза",
    category: "dish",
    description: "Шесть японских пельменей с хрустящей корочкой, свининой и капустой.",
    price: 320,
    ingredients: ["Тесто", "Свинина", "Капуста", "Имбирь", "Понзу"],
    image: image("dish", 6),
  },
  {
    id: 7,
    name: "Бибимбап",
    category: "dish",
    description: "Корейский рис с говядиной, овощами, яйцом и пастой кочудян.",
    price: 460,
    ingredients: ["Рис", "Говядина", "Яйцо", "Овощи", "Кочудян"],
    image: image("dish", 7),
  },
  {
    id: 8,
    name: "Фо бо",
    category: "dish",
    description: "Вьетнамский суп с говядиной, рисовой лапшой, зеленью и ростками.",
    price: 450,
    ingredients: ["Говядина", "Рисовая лапша", "Кинза", "Ростки", "Лайм"],
    image: image("dish", 8),
  },
  {
    id: 9,
    name: "Мисо-суп",
    category: "dish",
    description: "Лёгкий японский суп с мисо, тофу, водорослями вакаме и луком.",
    price: 180,
    ingredients: ["Паста мисо", "Тофу", "Вакаме", "Зелёный лук"],
    image: image("dish", 9),
  },
  {
    id: 10,
    name: "Курица терияки",
    category: "dish",
    description: "Сочная курица в соусе терияки с рисом, брокколи и кунжутом.",
    price: 440,
    ingredients: ["Курица", "Рис", "Брокколи", "Терияки", "Кунжут"],
    image: image("dish", 10),
  },
  {
    id: 11,
    name: "Курица кацу карри",
    category: "dish",
    description: "Хрустящая курица в панировке с японским карри, рисом и капустой.",
    price: 460,
    ingredients: ["Курица", "Панко", "Рис", "Японское карри", "Капуста"],
    image: image("dish", 11),
  },
  {
    id: 12,
    name: "Чапче с говядиной",
    category: "dish",
    description: "Корейская стеклянная лапша с говядиной, шиитаке и сезонными овощами.",
    price: 450,
    ingredients: ["Стеклянная лапша", "Говядина", "Шиитаке", "Шпинат", "Кунжут"],
    image: image("dish", 12),
  },
  {
    id: 13,
    name: "Спринг-роллы с креветками",
    category: "dish",
    description: "Четыре хрустящих ролла с креветками, овощами и ароматной зеленью.",
    price: 350,
    ingredients: ["Креветки", "Овощи", "Рисовая бумага", "Кинза", "Кунжут"],
    image: image("dish", 13),
  },
  {
    id: 14,
    name: "Димсам хар гоу",
    category: "dish",
    description: "Шесть нежных китайских димсамов с сочной креветкой.",
    price: 390,
    ingredients: ["Креветки", "Тесто димсам", "Бамбуковые побеги", "Кунжутное масло"],
    image: image("dish", 14),
  },
  {
    id: 15,
    name: "Кунг пао с курицей",
    category: "dish",
    description: "Пряная сычуаньская курица с арахисом, перцем и зелёным луком.",
    price: 440,
    ingredients: ["Курица", "Арахис", "Болгарский перец", "Чили", "Соевый соус"],
    image: image("dish", 15),
  },
  {
    id: 16,
    name: "Вок-лапша с курицей",
    category: "dish",
    description: "Пшеничная лапша вок с курицей, пак-чой, овощами и грибами.",
    price: 420,
    ingredients: ["Пшеничная лапша", "Курица", "Пак-чой", "Грибы", "Кунжут"],
    image: image("dish", 16),
  },
  {
    id: 17,
    name: "Матча-латте",
    category: "drink",
    description: "Церемониальная матча на молоке с нежной пеной.",
    price: 220,
    ingredients: ["Матча", "Молоко"],
    image: image("drink", 1),
    featured: true,
  },
  {
    id: 18,
    name: "Молочный улун",
    category: "drink",
    description: "Ароматный китайский чай с мягким сливочным послевкусием.",
    price: 180,
    ingredients: ["Чай улун"],
    image: image("drink", 2),
  },
  {
    id: 19,
    name: "Юдзу-лимонад",
    category: "drink",
    description: "Освежающий японский цитрусовый лимонад с мятой.",
    price: 210,
    ingredients: ["Юдзу", "Газированная вода", "Мята"],
    image: image("drink", 3),
  },
  {
    id: 20,
    name: "Имбирный чай",
    category: "drink",
    description: "Согревающий чай со свежим имбирём, лимоном и мёдом.",
    price: 190,
    ingredients: ["Имбирь", "Мёд", "Лимон", "Чай"],
    image: image("drink", 4),
  },
  {
    id: 21,
    name: "Бабл-ти",
    category: "drink",
    description: "Холодный молочный чай с тапиокой и коричневым сахаром.",
    price: 220,
    ingredients: ["Чай", "Молоко", "Тапиока", "Коричневый сахар"],
    image: image("drink", 5),
    featured: true,
  },
  {
    id: 22,
    name: "Таро-латте",
    category: "drink",
    description: "Нежный холодный латте из таро с мягкой сливочной текстурой.",
    price: 210,
    ingredients: ["Таро", "Молоко", "Лёд"],
    image: image("drink", 6),
  },
  {
    id: 23,
    name: "Холодный жасминовый чай",
    category: "drink",
    description: "Чистый освежающий чай с тонким жасминовым ароматом.",
    price: 170,
    ingredients: ["Жасминовый чай", "Лёд", "Жасмин"],
    image: image("drink", 7),
  },
  {
    id: 24,
    name: "Личи-лимонад",
    category: "drink",
    description: "Газированный напиток с личи, мятой и деликатной сладостью.",
    price: 220,
    ingredients: ["Личи", "Газированная вода", "Мята", "Лёд"],
    image: image("drink", 8),
  },
  {
    id: 25,
    name: "Мотти ассорти",
    category: "dessert",
    description: "Три рисовых пирожных с манго, матчей и чёрным кунжутом.",
    price: 260,
    ingredients: ["Клейкий рис", "Манго", "Матча", "Кунжут"],
    image: image("dessert", 1),
    featured: true,
  },
  {
    id: 26,
    name: "Манго-пудинг",
    category: "dessert",
    description: "Нежный пудинг на кокосовом молоке со свежим манго и чиа.",
    price: 240,
    ingredients: ["Манго", "Кокосовое молоко", "Чиа"],
    image: image("dessert", 2),
  },
  {
    id: 27,
    name: "Тайяки",
    category: "dessert",
    description: "Тёплая японская вафля-рыбка с начинкой из красной фасоли анко.",
    price: 200,
    ingredients: ["Тесто", "Паста анко", "Мёд"],
    image: image("dessert", 3),
  },
  {
    id: 28,
    name: "Чизкейк матча",
    category: "dessert",
    description: "Воздушный чизкейк с зелёным чаем матча и хрустящей основой.",
    price: 280,
    ingredients: ["Сливочный сыр", "Матча", "Печенье"],
    image: image("dessert", 4),
  },
  {
    id: 29,
    name: "Клейкий рис с манго",
    category: "dessert",
    description: "Тайский клейкий рис на кокосовом молоке со спелым манго.",
    price: 250,
    ingredients: ["Клейкий рис", "Манго", "Кокосовое молоко", "Кунжут"],
    image: image("dessert", 5),
  },
  {
    id: 30,
    name: "Данго",
    category: "dessert",
    description: "Японские рисовые шарики на шпажке под карамельно-соевым соусом.",
    price: 190,
    ingredients: ["Рисовая мука", "Соевый соус", "Сахар", "Кунжут"],
    image: image("dessert", 6),
  },
  {
    id: 31,
    name: "Кокосовая тапиока",
    category: "dessert",
    description: "Кокосовый пудинг с шариками тапиоки и сочным манго.",
    price: 230,
    ingredients: ["Кокосовое молоко", "Тапиока", "Манго"],
    image: image("dessert", 7),
  },
  {
    id: 32,
    name: "Банан в темпуре",
    category: "dessert",
    description: "Хрустящий банан в темпуре с кокосовым мороженым и карамелью.",
    price: 230,
    ingredients: ["Банан", "Панировка", "Кокосовое мороженое", "Карамель"],
    image: image("dessert", 8),
  },
];

export const getProduct = (id: number): Product | undefined =>
  PRODUCTS.find((p) => p.id === id);

export const byCategory = (category: Category): Product[] =>
  PRODUCTS.filter((p) => p.category === category);

export const featured = (): Product[] => PRODUCTS.filter((p) => p.featured);

export const formatPrice = (value: number): string => `${value} ₴`;
