from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0012_outbox_settled_status"),
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
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="pending",
                max_length=12,
            ),
        ),
    ]
