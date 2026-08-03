from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0005_remove_orderoutbox_orders_orde_status_01745b_idx_and_more")]

    operations = [
        migrations.AddField(
            model_name="orderoutbox",
            name="snapshot",
            field=models.BooleanField(default=False),
        ),
    ]
