from django.db import migrations

STAFF_GROUPS = ["restaurant_operator", "restaurant_manager", "restaurant_employee"]


def clear_staff_groups(apps, schema_editor):
    """
    a superuser already holds every capability, so a staff group only made the state unfixable

    the role service refuses a superuser target, so these memberships could not be removed through any supported path once promotion left them behind
    """
    User = apps.get_model("accounts", "User")
    Group = apps.get_model("auth", "Group")
    groups = list(Group.objects.filter(name__in=STAFF_GROUPS))
    if not groups:
        return
    for user in User.objects.filter(is_superuser=True, groups__in=groups).distinct():
        user.groups.remove(*groups)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_role_audit_transition")]
    # no reverse: restoring a role nobody can name would be a guess at who held what
    operations = [migrations.RunPython(clear_staff_groups, migrations.RunPython.noop)]
