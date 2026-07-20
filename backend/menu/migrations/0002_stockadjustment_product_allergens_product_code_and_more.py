import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _backfill_code(apps, schema_editor):
    """Derive a stable code from the image filename (products/dish_1.webp -> dish_1);
    fall back to <category>_<id> for rows without an image or on collision. Matches
    seed_menu's code derivation so a re-seed upserts the same rows."""
    Product = apps.get_model("menu", "Product")
    seen: set[str] = set()
    for product in Product.objects.all().iterator():
        name = str(product.image or "")
        code = name.rsplit("/", 1)[-1].rsplit(".", 1)[0] if name else ""
        if not code or code in seen:
            code = f"{product.category}_{product.id}"
        seen.add(code)
        Product.objects.filter(pk=product.pk).update(code=code)


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StockAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("old_quantity", models.PositiveIntegerField()),
                ("new_quantity", models.PositiveIntegerField()),
                ("reason", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="product",
            name="allergens",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="product",
            name="stock_quantity",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("stock_quantity__gte", 0)), name="product_stock_gte_0"
            ),
        ),
        # code: add as a plain CharField (no index → no _like index collision on
        # the later AlterField), backfill existing rows, then switch to a unique SlugField
        migrations.AddField(
            model_name="product",
            name="code",
            field=models.CharField(default="", max_length=40),
        ),
        migrations.RunPython(_backfill_code, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="product",
            name="code",
            field=models.SlugField(default="", max_length=40, unique=True),
        ),
        migrations.AddField(
            model_name="stockadjustment",
            name="product",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="stock_adjustments", to="menu.product"
            ),
        ),
        migrations.AddField(
            model_name="stockadjustment",
            name="staff",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
