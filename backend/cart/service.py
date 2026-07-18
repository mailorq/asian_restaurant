import redis.asyncio as aioredis
from django.conf import settings


CART_TTL = 60 * 60 * 24 * 14  # 14 days; refreshed on every write
MAX_QTY = 50


def redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _key(user_id: int) -> str:
    return f"cart:u:{user_id}"


async def get_items(r: aioredis.Redis, user_id: int) -> dict[int, int]:
    raw = await r.hgetall(_key(user_id))
    return {int(k): int(v) for k, v in raw.items()}


async def add(r: aioredis.Redis, user_id: int, product_id: int, delta: int) -> int:
    key = _key(user_id)
    qty = await r.hincrby(key, product_id, delta)
    if qty > MAX_QTY:
        await r.hset(key, product_id, MAX_QTY)
        qty = MAX_QTY
    if qty <= 0:
        await r.hdel(key, product_id)
        qty = 0
    await r.expire(key, CART_TTL)
    return qty


async def set_qty(r: aioredis.Redis, user_id: int, product_id: int, quantity: int) -> None:
    key = _key(user_id)
    if quantity <= 0:
        await r.hdel(key, product_id)
        return
    await r.hset(key, product_id, min(quantity, MAX_QTY))
    await r.expire(key, CART_TTL)


async def remove(r: aioredis.Redis, user_id: int, *product_ids: int) -> None:
    if product_ids:
        await r.hdel(_key(user_id), *product_ids)


async def clear(r: aioredis.Redis, user_id: int) -> None:
    await r.delete(_key(user_id))
