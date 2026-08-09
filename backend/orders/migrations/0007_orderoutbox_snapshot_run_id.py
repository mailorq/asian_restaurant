from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0006_orderoutbox_snapshot")]

    operations = [
        migrations.AddField(
            model_name="orderoutbox",
            name="snapshot_run_id",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
