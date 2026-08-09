from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0003_snapshotexpectation")]

    operations = [
        migrations.AddField(
            model_name="operationorder",
            name="payment_method",
            field=models.CharField(blank=True, max_length=8),
        ),
    ]
