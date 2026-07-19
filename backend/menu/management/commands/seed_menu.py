import importlib.util
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from menu.models import Ingredient, Product

SEED_DIR = Path(settings.BASE_DIR) / "seed"
SOURCE_IMAGES = SEED_DIR / "images" / "optimized"
DEFAULT_STOCK = 50


def _load_products() -> list[dict]:
    path = SEED_DIR / "products_data.py"
    spec = importlib.util.spec_from_file_location("products_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PRODUCTS_DATA


def _split_allergens(description: str) -> tuple[str, str]:
    marker = "Аллергены:"
    if marker not in description:
        return description.strip(), ""
    desc, allergens = description.split(marker, 1)
    allergens = allergens.strip()
    if allergens.lower().startswith("отсутств"):
        allergens = ""
    return desc.strip(), allergens


class Command(BaseCommand):
    help = "Seed products/ingredients from backend/seed/products_data.py (idempotent, keyed by code)."

    def handle(self, *args, **options) -> None:
        media_products = Path(settings.MEDIA_ROOT) / "products"
        media_products.mkdir(parents=True, exist_ok=True)
        created = updated = 0

        for row in _load_products():
            basename = Path(row["image"]).name
            code = Path(basename).stem  # dish_1, drink_4, dessert_2
            source = SOURCE_IMAGES / basename
            if source.exists():
                shutil.copy2(source, media_products / basename)

            description, allergens = _split_allergens(row["description"])
            product, is_new = Product.objects.update_or_create(
                code=code,
                defaults={
                    "category": row["category"],
                    "name": row["name"],
                    "description": description,
                    "allergens": allergens,
                    "price": row["price"],
                    "image": row["image"],
                    "is_active": row["is_active"],
                    "is_featured": row["is_featured"],
                    "stock_quantity": row.get("stock", DEFAULT_STOCK),
                },
            )
            product.ingredients.set(
                Ingredient.objects.get_or_create(name=name)[0] for name in row["ingredients"]
            )
            created += int(is_new)
            updated += int(not is_new)

        self.stdout.write(self.style.SUCCESS(f"seeded: {created} new, {updated} updated"))
