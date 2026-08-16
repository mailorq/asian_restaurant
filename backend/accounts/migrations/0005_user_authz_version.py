from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_user_customer_version")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="authz_version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
