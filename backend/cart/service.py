import asyncio

import redis.asyncio as aioredis
from django.conf import settings
from ninja.errors import HttpError
from redis.exceptions import RedisError

from menu.models import Product


CART_TTL = 60 * 60 * 24 * 14  # 14 days; refreshed on every mutation
MAX_QTY = 50
VERSION_FIELD = "v"

# Atomic compare-and-set: optionally guards on expected version, applies the op,
# bumps the version and refreshes the TTL in a single round-trip.
#   KEYS[1] = cart key
#   ARGV[1] = expected version (-1 skips the check)
#   ARGV[2] = ttl seconds
#   ARGV[3] = op: add | set | del | clear
#   ARGV[4] = product id (add | set | del)
#   ARGV[5] = quantity (add | set)
#   ARGV[6] = max qty
# returns {status, version}; status -1 means version conflict (version is current).
_CAS_LUA = """
local key = KEYS[1]
local cur = tonumber(redis.call('HGET', key, 'v')) or 0
local expected = tonumber(ARGV[1])
if expected >= 0 and expected ~= cur then
  return {-1, cur}
end
local op = ARGV[3]
local maxq = tonumber(ARGV[6])
if op == 'add' then
  local pid = ARGV[4]
  local q = redis.call('HINCRBY', key, pid, tonumber(ARGV[5]))
  if q > maxq then redis.call('HSET', key, pid, maxq)
  elseif q <= 0 then redis.call('HDEL', key, pid) end
elseif op == 'set' then
  local pid = ARGV[4]
  local q = tonumber(ARGV[5])
  if q <= 0 then
    redis.call('HDEL', key, pid)
  else
    if q > maxq then q = maxq end
    redis.call('HSET', key, pid, q)
  end
elseif op == 'del' then
  redis.call('HDEL', key, ARGV[4])
elseif op == 'clear' then
  redis.call('DEL', key)
  return {0, 0}
end
local nv = cur + 1
redis.call('HSET', key, 'v', nv)
redis.call('EXPIRE', key, tonumber(ARGV[2]))
return {0, nv}
"""

# Atomic guest->user merge: fold every guest item into the user hash (capped),
# drop the guest key and bump the user version — all in one script so two
# concurrent post-login requests cannot merge the same items twice.
#   KEYS[1] = destination (user) key, KEYS[2] = source (guest) key
#   ARGV[1] = ttl seconds, ARGV[2] = max qty
# returns the destination version.
_MERGE_LUA = """
local dst, src = KEYS[1], KEYS[2]
local maxq = tonumber(ARGV[2])
local data = redis.call('HGETALL', src)
redis.call('DEL', src)
local moved = false
for i = 1, #data, 2 do
  if data[i] ~= 'v' then
    local q = redis.call('HINCRBY', dst, data[i], tonumber(data[i + 1]))
    if q > maxq then redis.call('HSET', dst, data[i], maxq) end
    moved = true
  end
end
local cur = tonumber(redis.call('HGET', dst, 'v')) or 0
if moved then
  cur = cur + 1
  redis.call('HSET', dst, 'v', cur)
  redis.call('EXPIRE', dst, tonumber(ARGV[1]))
end
return cur
"""

# Server-side reconciliation against live stock: remove the listed ids, clamp the
# listed (pid, qty) pairs, and — when anything actually changed — atomically bump
# the version so the optimistic-lock contract holds. Returns the current version.
#   KEYS[1] = cart key
#   ARGV[1] = ttl seconds
#   ARGV[2] = number of remove ids R
#   ARGV[3 .. 2+R] = product ids to remove
#   ARGV[3+R ..] = flattened (pid, qty) clamp pairs
_RECONCILE_LUA = """
local key = KEYS[1]
local r = tonumber(ARGV[2])
local idx = 3
local changed = false
for i = 1, r do
  redis.call('HDEL', key, ARGV[idx])
  idx = idx + 1
  changed = true
end
while idx < #ARGV do
  redis.call('HSET', key, ARGV[idx], ARGV[idx + 1])
  idx = idx + 2
  changed = true
end
local cur = tonumber(redis.call('HGET', key, 'v')) or 0
if changed then
  cur = cur + 1
  redis.call('HSET', key, 'v', cur)
  redis.call('EXPIRE', key, tonumber(ARGV[1]))
end
return cur
"""

# One client per running event loop: a redis.asyncio client (and its pool) is
# bound to the loop it was created on. Under uvicorn there is a single persistent
# loop (one client); the Django dev server runs each request in a fresh loop, so
# we key by loop and prune clients whose loop has since closed.
_clients: dict[asyncio.AbstractEventLoop, aioredis.Redis] = {}


class CartConflict(Exception):
    """Raised when a write's expected version no longer matches the stored one."""

    def __init__(self, version: int) -> None:
        self.version = version
        super().__init__(f"cart version conflict, current={version}")


def _redis() -> aioredis.Redis:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        for dead in [ev for ev in _clients if ev.is_closed()]:
            _clients.pop(dead, None)
        client = aioredis.from_url(settings.CART_REDIS_URL, decode_responses=True)
        _clients[loop] = client
    return client


def user_key(user_id: int) -> str:
    return f"cart:u:{user_id}"


def guest_key(cart_id: str) -> str:
    return f"cart:g:{cart_id}"


async def read(key: str) -> tuple[dict[int, int], int]:
    try:
        raw = await _redis().hgetall(key)
    except RedisError:
        raise HttpError(503, "Корзина временно недоступна. Повторите позже.")
    version = int(raw.pop(VERSION_FIELD, 0) or 0)
    items = {int(k): int(v) for k, v in raw.items()}
    return items, version


async def _apply(key: str, expected: int | None, op: str, product_id: int = 0, quantity: int = 0) -> int:
    argv = [
        -1 if expected is None else int(expected),
        CART_TTL,
        op,
        product_id,
        quantity,
        MAX_QTY,
    ]
    try:
        status, version = await _redis().eval(_CAS_LUA, 1, key, *argv)
    except RedisError:
        raise HttpError(503, "Корзина временно недоступна. Повторите позже.")
    if int(status) == -1:
        raise CartConflict(int(version))
    return int(version)


async def add(key: str, product_id: int, quantity: int, expected: int | None) -> int:
    return await _apply(key, expected, "add", product_id, quantity)


async def set_qty(key: str, product_id: int, quantity: int, expected: int | None) -> int:
    return await _apply(key, expected, "set", product_id, quantity)


async def remove(key: str, product_id: int, expected: int | None) -> int:
    return await _apply(key, expected, "del", product_id)


async def clear(key: str, expected: int | None) -> int:
    return await _apply(key, expected, "clear")


async def delete(key: str) -> None:
    try:
        await _redis().delete(key)
    except RedisError:
        raise HttpError(503, "Корзина временно недоступна. Повторите позже.")


async def merge_guest_into_user(src_key: str, dst_key: str) -> None:
    try:
        await _redis().eval(_MERGE_LUA, 2, dst_key, src_key, CART_TTL, MAX_QTY)
    except RedisError:
        raise HttpError(503, "Корзина временно недоступна. Повторите позже.")


async def _reconcile(key: str, remove_ids: list[int], set_map: dict[int, int]) -> int:
    # server-side reconciliation against live stock; atomically bumps the version
    argv: list[int] = [CART_TTL, len(remove_ids), *remove_ids]
    for product_id, quantity in set_map.items():
        argv += [product_id, quantity]
    try:
        version = await _redis().eval(_RECONCILE_LUA, 1, key, *argv)
    except RedisError:
        raise HttpError(503, "Корзина временно недоступна. Повторите позже.")
    return int(version)


async def render(key: str, items: dict[int, int], version: int) -> dict:
    if not items:
        return {"version": version, "items": [], "total": 0.0, "count": 0, "adjustments": [], "removed_items": []}

    products = {p.id: p async for p in Product.objects.filter(id__in=list(items))}
    lines: list[dict] = []
    adjustments: list[dict] = []
    removed: list[dict] = []
    remove_ids: list[int] = []
    set_map: dict[int, int] = {}
    total = 0.0
    count = 0

    for product_id, quantity in items.items():
        product = products.get(product_id)
        if product is None or not product.is_active:
            removed.append({"product_id": product_id, "name": product.name if product else "", "reason": "unavailable"})
            remove_ids.append(product_id)
            continue

        cap = min(MAX_QTY, product.stock_quantity)
        if cap <= 0:
            removed.append({"product_id": product_id, "name": product.name, "reason": "out_of_stock"})
            remove_ids.append(product_id)
            continue

        effective = quantity
        if quantity > cap:
            effective = cap
            set_map[product_id] = cap
            adjustments.append(
                {"product_id": product_id, "name": product.name, "from_qty": quantity, "to_qty": cap, "reason": "stock"}
            )

        price = float(product.price)
        total += price * effective
        count += effective
        lines.append(
            {
                "product_id": product_id,
                "name": product.name,
                "category": product.category,
                "price": price,
                "quantity": effective,
                "image": product.image.url if product.image else None,
                "available": True,
            }
        )

    if remove_ids or set_map:
        version = await _reconcile(key, remove_ids, set_map)

    return {
        "version": version,
        "items": lines,
        "total": round(total, 2),
        "count": count,
        "adjustments": adjustments,
        "removed_items": removed,
    }


async def snapshot(key: str) -> dict:
    # frozen, server-priced view for checkout; reuses the same stock reconciliation
    items, version = await read(key)
    return await render(key, items, version)
