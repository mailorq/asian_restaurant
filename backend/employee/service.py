from django.contrib.auth import get_user_model
from django.db import transaction

from accounts.models import EmployeeRoleAudit, has_operations_role
from accounts.roles import roles_of
from orders.models import OrderOutbox

AUTHZ_EVENT = "identity.authz_changed"


def emit_authz(user) -> None:
    OrderOutbox.objects.create(
        aggregate_id=str(user.id),
        aggregate_version=user.authz_version,
        event_type=AUTHZ_EVENT,
        routing_key=AUTHZ_EVENT,
        # role_active stays for consumers that predate roles; the contract ignores unknown fields, so the two can travel together and no second event type is needed
        payload={"subject_id": user.id, "authz_version": user.authz_version,
                 "role_active": bool(roles_of(user)), "roles": roles_of(user),
                 "user_active": user.is_active},
    )


def _other_active_superuser_exists(exclude_pk) -> bool:
    return (
        get_user_model().objects.filter(is_superuser=True, is_active=True)
        .exclude(pk=exclude_pk).exists()
    )


@transaction.atomic
def set_superuser(actor, target, is_superuser: bool):
    user = get_user_model().objects.select_for_update().get(pk=target.pk)
    if user.is_superuser == is_superuser:
        return user
    if not is_superuser and not _other_active_superuser_exists(user.pk):
        raise ValueError("нельзя снять права у последнего активного суперпользователя")
    user.is_superuser = is_superuser
    user.authz_version += 1
    user.save(update_fields=["is_superuser", "authz_version"])
    EmployeeRoleAudit.objects.create(
        actor=actor,
        target=user,
        action=EmployeeRoleAudit.Action.GRANT if is_superuser else EmployeeRoleAudit.Action.REVOKE,
    )
    emit_authz(user)
    return user


@transaction.atomic
def set_active(actor, target, active: bool):
    # is_active is authorization state: deactivating an operations-capable user must revoke
    # their access, so bump the version and emit — customers carry no operations access
    user = get_user_model().objects.select_for_update().get(pk=target.pk)
    if user.is_active == active:
        return user
    if not active and user.is_superuser and not _other_active_superuser_exists(user.pk):
        raise ValueError("нельзя деактивировать последнего активного суперпользователя")
    user.is_active = active
    if has_operations_role(user):
        user.authz_version += 1
        user.save(update_fields=["is_active", "authz_version"])
        emit_authz(user)
    else:
        user.save(update_fields=["is_active"])
    return user


def emit_authz_state(user) -> None:
    # re-publish current authorization state (idempotent at the same version downstream)
    emit_authz(user)
