from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0009_command_envelope_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="operationsoutbox",
            name="publish_attempted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="operationsoutbox",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("published", "Published"),
                    ("suppressed", "Suppressed"),
                ],
                db_index=True,
                default="pending",
                max_length=12,
            ),
        ),
    ]
