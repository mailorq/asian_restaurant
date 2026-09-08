import datetime as dt
import threading
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from event_contracts import OrderTransitionRequestedData

from accounts.roles import StaffRole
from cart import service as cart_service
from menu.models import Product
from orders import commands
from orders import service as order_service
from orders.models import CommandInbox, OrderOutbox, OrderStatusHistory


def _actor():
    account = get_user_model().objects.create_user(
        username="+79990000777", password="Pass!2345", phone="+79990000777"
    )
    account.groups.add(Group.objects.get_or_create(name=StaffRole.MANAGER)[0])
    account.authz_version += 1
    account.save(update_fields=["authz_version"])
    account.refresh_from_db()
    return account


def _order(actor):
    product = Product.objects.create(
        code="conc_1", category="dish", name="Рамен", description="d",
        price="100.00", stock_quantity=10, is_active=True,
    )
    key = cart_service.user_key(actor.id)
    cart_service._sync_redis().hset(
        key, mapping={str(product.id): 2, cart_service.VERSION_FIELD: 1}
    )
    return order_service.checkout(actor, "ул. Пушкина, 12", "cash", "idem-conc-1")


@pytest.mark.django_db(transaction=True)
def test_two_deliveries_of_one_command_apply_it_once():
    actor = _actor()
    order = _order(actor)
    data = OrderTransitionRequestedData(
        command_id=uuid.uuid4(), actor_id=actor.id, actor_authz_version=actor.authz_version,
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=60),
        order_id=order.id, expected_status="created", target_status="confirmed",
    )
    request_event_id, correlation_id = uuid.uuid4(), uuid.uuid4()

    results, errors = [], []
    start = threading.Barrier(2)

    def deliver():
        try:
            start.wait(timeout=15)
            results.append(
                commands.apply_transition_command(
                    data, request_event_id=request_event_id, correlation_id=correlation_id
                )
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=deliver) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=40)

    assert not errors, errors
    assert len(results) == 2
    assert sorted(r.replayed for r in results) == [False, True]
    assert [r.data for r in results][0] == [r.data for r in results][1]

    order.refresh_from_db()
    assert order.status == "confirmed"
    assert CommandInbox.objects.filter(command_id=data.command_id).count() == 1
    assert OrderOutbox.objects.filter(event_type="orders.transition.succeeded.v1").count() == 1
    assert OrderStatusHistory.objects.filter(order=order, to_status="confirmed").count() == 1
