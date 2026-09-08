from django.db import migrations

LEGACY = "restaurant_employee"
OPERATOR = "restaurant_operator"
MANAGER = "restaurant_manager"


def split_roles(apps, schema_editor):
    """existing staff become managers, not operators

    the legacy group granted stock and customer data, so mapping it to the narrower role would
    silently remove access people already have. the legacy group is left in place until an
    operator has confirmed the projection converged
    """
    Group = apps.get_model("auth", "Group")
    manager, _ = Group.objects.get_or_create(name=MANAGER)
    Group.objects.get_or_create(name=OPERATOR)
    legacy = Group.objects.filter(name=LEGACY).first()
    if legacy is None:
        return
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(groups=legacy):
        user.groups.add(manager)


def merge_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    legacy, _ = Group.objects.get_or_create(name=LEGACY)
    manager = Group.objects.filter(name=MANAGER).first()
    if manager is None:
        return
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(groups=manager):
        user.groups.add(legacy)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_user_authz_version")]
    operations = [migrations.RunPython(split_roles, merge_roles)]
