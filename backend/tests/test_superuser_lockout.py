"""
two superusers must not be able to demote each other into an empty room

the guard reads the set of active superusers; without locking that set, each transaction sees the
other still active and both commit
"""

import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connections, transaction

from employee import service


@pytest.mark.django_db(transaction=True)
def test_only_one_of_two_concurrent_demotions_can_win():
    User = get_user_model()
    first = User.objects.create_superuser(username="+79990000201", password="Pass!2345")
    second = User.objects.create_superuser(username="+79990000202", password="Pass!2345")
    ready = threading.Barrier(2)
    outcomes = []

    def demote(actor, target):
        try:
            ready.wait(timeout=10)
            with transaction.atomic():
                service.set_superuser(actor=actor, target=target, is_superuser=False)
            outcomes.append("committed")
        except Exception as exc:
            outcomes.append(type(exc).__name__)
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=demote, args=(first, second)),
        threading.Thread(target=demote, args=(second, first)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    left = User.objects.filter(is_superuser=True, is_active=True).count()
    assert left >= 1, f"both demotions went through: {outcomes}"
    assert outcomes.count("committed") <= 1, outcomes
