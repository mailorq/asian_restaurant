import pytest
import redis as redis_sync
from django.contrib.auth import get_user_model

from cart import service
from menu.models import Product


TEST_CART_REDIS_URL = "redis://redis:6379/15"


@pytest.fixture(autouse=True)
def cart_redis(settings):
    # isolate cart data on a throwaway redis db and force the async client to
    # rebind to it (the module singleton is otherwise cached per event loop)
    settings.CART_REDIS_URL = TEST_CART_REDIS_URL
    service._clients.clear()
    conn = redis_sync.from_url(TEST_CART_REDIS_URL)
    conn.flushdb()
    yield
    try:
        conn.flushdb()
    finally:
        conn.close()
    service._clients.clear()


@pytest.fixture
def api(client):
    # the sync test client may run each async request in a fresh event loop, so
    # drop the cached redis client before every call to rebind it to that loop
    class _Api:
        def _reset(self):
            service._clients.clear()

        def get(self, *a, **k):
            self._reset()
            return client.get(*a, **k)

        def post(self, *a, **k):
            self._reset()
            return client.post(*a, **k)

        def put(self, *a, **k):
            self._reset()
            return client.put(*a, **k)

        def delete(self, *a, **k):
            self._reset()
            return client.delete(*a, **k)

        def force_login(self, user):
            client.force_login(user)

        @property
        def cookies(self):
            return client.cookies

    return _Api()


@pytest.fixture
def make_product(db):
    counter = {"n": 0}

    def _make(name="Товар", price="100.00", stock=50, is_active=True, category="dish"):
        counter["n"] += 1
        n = counter["n"]
        return Product.objects.create(
            code=f"test_{n}",
            category=category,
            name=name,
            description="desc",
            price=price,
            stock_quantity=stock,
            is_active=is_active,
        )

    return _make


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="+79990000001",
        password="Pass!2345",
        first_name="Иван",
    )
