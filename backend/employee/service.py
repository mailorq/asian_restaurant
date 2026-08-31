from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from accounts.models import EMPLOYEE_GROUP, EmployeeRoleAudit, has_operations_role
from orders.models import OrderOutbox

AUTHZ_EVENT = "identity.authz_changed"


def _emit_authz(user) -> None:
    OrderOutbox.objects.create(
        aggregate_id=str(user.id),
        aggregate_version=user.authz_version,
        event_type=AUTHZ_EVENT,
        routing_key=AUTHZ_EVENT,
        payload={"subject_id": user.id, "authz_version": user.authz_version,
                 "role_active": has_operations_role(user), "user_active": user.is_active},
    )


@transaction.atomic
def set_employee_role(actor, target, grant: bool):
    # the only authorized path to change staff membership. lock + re-read so concurrent
    # grant/revoke serialize; a no-op change bumps no version, writes no audit, emits nothing
    user = get_user_model().objects.select_for_update().get(pk=target.pk)
    currently = user.groups.filter(name=EMPLOYEE_GROUP).exists()
    if grant == currently:
        return user
    group, _ = Group.objects.get_or_create(name=EMPLOYEE_GROUP)
    if grant:
        user.groups.add(group)
        action = EmployeeRoleAudit.Action.GRANT
    else:
        user.groups.remove(group)
        action = EmployeeRoleAudit.Action.REVOKE
    user.authz_version += 1
    user.save(update_fields=["authz_version"])
    EmployeeRoleAudit.objects.create(actor=actor, target=user, action=action)
    _emit_authz(user)
    return user


@transaction.atomic
def set_superuser(actor, target, is_superuser: bool):
    user = get_user_model().objects.select_for_update().get(pk=target.pk)
    if user.is_superuser == is_superuser:
        return user
    user.is_superuser = is_superuser
    user.authz_version += 1
    user.save(update_fields=["is_superuser", "authz_version"])
    EmployeeRoleAudit.objects.create(
        actor=actor,
        target=user,
        action=EmployeeRoleAudit.Action.GRANT if is_superuser else EmployeeRoleAudit.Action.REVOKE,
    )
    _emit_authz(user)
    return user


@transaction.atomic
def set_active(actor, target, active: bool):
    # is_active is authorization state: deactivating an operations-capable user must revoke
    # their access, so bump the version and emit — customers carry no operations access
    user = get_user_model().objects.select_for_update().get(pk=target.pk)
    if user.is_active == active:
        return user
    user.is_active = active
    if has_operations_role(user):
        user.authz_version += 1
        user.save(update_fields=["is_active", "authz_version"])
        _emit_authz(user)
    else:
        user.save(update_fields=["is_active"])
    return user


def emit_authz_state(user) -> None:
    # re-publish current authorization state (idempotent at the same version downstream)
    _emit_authz(user)
