from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0011_outbox_lease_token"),
    ]

    operations = [
        migrations.AlterField(
            model_name="operationsoutbox",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("published", "Published"),
                    ("suppressed", "Suppressed"),
                    ("settled", "Settled"),
                ],
                db_index=True,
                default="pending",
                max_length=12,
            ),
        ),
    ]
