from ninja import Schema


class ProductOut(Schema):
    id: int
    code: str
    category: str
    name: str
    description: str
    price: float
    image: str | None = None
    ingredients: list[str] = []
    allergens: list[str] = []
    is_featured: bool
    available: bool
    stock: int

    @staticmethod
    def resolve_image(obj) -> str | None:
        return obj.image.url if obj.image else None

    @staticmethod
    def resolve_ingredients(obj) -> list[str]:
        return [i.name for i in obj.ingredients.all()]

    @staticmethod
    def resolve_allergens(obj) -> list[str]:
        return [a.strip() for a in obj.allergens.split(",") if a.strip()] if obj.allergens else []

    @staticmethod
    def resolve_available(obj) -> bool:
        return obj.available

    @staticmethod
    def resolve_stock(obj) -> int:
        return obj.stock_quantity
