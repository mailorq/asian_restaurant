from django.db import transaction

from accounts.models import User
from orders.models import OrderOutbox

CUSTOMER_EVENT = "identity.customer_changed"


def _emit(user: User, *, snapshot: bool = False) -> None:
    OrderOutbox.objects.create(
        aggregate_id=str(user.id),
        aggregate_version=user.customer_version,
        event_type=CUSTOMER_EVENT,
        routing_key=CUSTOMER_EVENT,
        snapshot=snapshot,
        payload={"customer_id": user.id, "name": user.first_name or "", "phone": user.phone or ""},
    )


def emit_customer_created(user: User) -> None:
    # called inside the registration transaction; initial customer state is v1
    _emit(user)


@transaction.atomic
def set_customer_profile(user_id: int, *, name: str | None = None, phone: str | None = None) -> User | None:
    user = User.objects.select_for_update().filter(id=user_id).first()
    if user is None:
        return None
    changed = False
    if name is not None and name != user.first_name:
        user.first_name = name
        changed = True
    if phone is not None and phone != user.phone:
        user.phone = phone
        changed = True
    if changed:
        user.customer_version += 1
        user.save(update_fields=["first_name", "phone", "customer_version"])
        _emit(user)
    return user


def emit_state(user: User, *, snapshot: bool = False) -> None:
    _emit(user, snapshot=snapshot)
