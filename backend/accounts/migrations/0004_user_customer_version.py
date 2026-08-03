from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_restaurant_employee_group")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="customer_version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
