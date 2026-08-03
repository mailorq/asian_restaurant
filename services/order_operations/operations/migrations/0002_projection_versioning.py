from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="customerprojection",
            name="aggregate_version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="inventoryprojection",
            name="aggregate_version",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
