from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0010_outbox_delivery_proof"),
    ]

    operations = [
        migrations.AddField(
            model_name="operationsoutbox",
            name="lease_token",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
