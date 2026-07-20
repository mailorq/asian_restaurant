from django.db import migrations

EMPLOYEE_GROUP = "restaurant_employee"


def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=EMPLOYEE_GROUP)


def delete_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=EMPLOYEE_GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_employeeroleaudit")]
    operations = [migrations.RunPython(create_group, delete_group)]
