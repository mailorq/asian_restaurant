"""
staff roles and what each may do

one group used to grant order handling, stock control and the whole customer directory at once.
these two split the duties: an operator moves orders, a manager also owns stock and customer data
"""

from django.contrib.auth.models import Group
from django.db import models, transaction


class NotAuthorized(Exception):
    pass


class StaffRole(models.TextChoices):
    OPERATOR = "restaurant_operator", "Оператор"
    MANAGER = "restaurant_manager", "Менеджер"


class Capability(models.TextChoices):
    ORDERS = "orders", "Заказы"
    INVENTORY = "inventory", "Склад"
    CUSTOMERS = "customers", "Клиенты"


CAPABILITIES = {
    StaffRole.OPERATOR: frozenset({Capability.ORDERS}),
    StaffRole.MANAGER: frozenset({Capability.ORDERS, Capability.INVENTORY, Capability.CUSTOMERS}),
}
LEGACY_GROUP = "restaurant_employee"


def staff_role(user) -> str | None:
    """
    the one staff group the user holds, or None

    a superuser holds no group and is handled by the capability check instead
    """
    if not getattr(user, "is_authenticated", False):
        return None
    names = {g.name for g in user.groups.all()} & set(StaffRole.values)
    if len(names) != 1:
        # more than one staff group is a broken grant, not a wider one
        return None
    return names.pop()


def roles_of(user) -> list[str]:
    """what a token and an authorization event should carry"""
    if getattr(user, "is_superuser", False):
        return [StaffRole.MANAGER]
    role = staff_role(user)
    return [role] if role else []


def has_capability(user, capability: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    role = staff_role(user)
    return bool(role and capability in CAPABILITIES[StaffRole(role)])


def is_staff_member(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or staff_role(user))


@transaction.atomic
def set_staff_role(*, actor, target, role: str | None):
    """
    the only authorized path to change staff membership

    locks the row so concurrent grants serialize, holds at most one role, and leaves the
    authorization version alone when the effective role did not change: bumping it would
    invalidate live tokens for nothing
    """
    from django.contrib.auth import get_user_model

    from accounts.models import EmployeeRoleAudit
    from employee.service import emit_authz

    if role is not None and role not in StaffRole.values:
        raise ValueError(f"unknown staff role: {role}")

    # the invariant belongs here, not only in the HTTP decorator: this is the documented single path, and a management command reaches it without passing through a view
    # actor and target are locked in one query by ascending pk, so two callers cannot take them in opposite order
    actor_pk = getattr(actor, "pk", None)
    locked = {
        row.pk: row
        for row in get_user_model().objects.select_for_update().order_by("pk")
        .filter(pk__in=[pk for pk in (actor_pk, target.pk) if pk is not None])
    }
    # re-read: the rights the caller's object was loaded with may already be gone
    fresh_actor = locked.get(actor_pk)
    if not (fresh_actor and fresh_actor.is_superuser and fresh_actor.is_active):
        raise NotAuthorized("only an active superuser may change a staff role")

    user = locked[target.pk]
    staff_groups = [*StaffRole.values, LEGACY_GROUP]
    # compare the membership that is actually there: a broken double grant resolves to no role, and comparing resolved roles would call clearing it a noop
    held = set(user.groups.filter(name__in=staff_groups).values_list("name", flat=True))
    wanted = {role} if role else set()
    if held == wanted:
        return user
    current = staff_role(user)

    user.groups.remove(*Group.objects.filter(name__in=staff_groups))
    if role is not None:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)

    user.authz_version += 1
    user.save(update_fields=["authz_version"])
    if current and role:
        action = EmployeeRoleAudit.Action.CHANGE
    elif role:
        action = EmployeeRoleAudit.Action.GRANT
    else:
        action = EmployeeRoleAudit.Action.REVOKE
    EmployeeRoleAudit.objects.create(
        actor=fresh_actor, target=user, action=action,
        from_role=current or "", to_role=role or "",
    )
    emit_authz(user)
    return user
