from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0006_snapshot_boundary")]

    operations = [
        migrations.CreateModel(
            name="EmployeeAuthorization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject_id", models.PositiveIntegerField(unique=True)),
                ("authz_version", models.PositiveIntegerField(default=0)),
                ("role_active", models.BooleanField(default=False)),
                ("user_active", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
