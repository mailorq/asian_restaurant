from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("menu", "0002_stockadjustment_product_allergens_product_code_and_more")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
