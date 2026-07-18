from ninja import Router
from ninja.errors import HttpError
from ninja.security import django_auth

from cart import service
from cart.schemas import AddItemIn, CartOut, SetQtyIn
from common.ratelimit import rate_limit
from menu.models import Product


router = Router(tags=["cart"], auth=django_auth)

WRITE_LIMIT = dict(scope="cart_write", limit=60, window=60)


async def _render(r, user_id: int) -> dict:
    items = await service.get_items(r, user_id)
    if not items:
        return {"items": [], "total": 0.0, "count": 0}

    products = {p.id: p async for p in Product.objects.filter(id__in=list(items))}
    stale = [pid for pid in items if pid not in products]
    if stale:
        await service.remove(r, user_id, *stale)

    lines, total, count = [], 0.0, 0
    for product_id, qty in items.items():
        product = products.get(product_id)
        if product is None:
            continue
        price = float(product.price)
        if product.is_active:
            total += price * qty
            count += qty
        lines.append(
            {
                "product_id": product_id,
                "name": product.name,
                "price": price,
                "quantity": qty,
                "image": product.image.url if product.image else None,
                "available": product.is_active,
            }
        )
    return {"items": lines, "total": total, "count": count}


@router.get("", response=CartOut)
async def get_cart(request):
    async with service.redis() as r:
        return await _render(r, request.auth.id)


@router.post("/items", response=CartOut)
@rate_limit(**WRITE_LIMIT)
async def add_item(request, data: AddItemIn):
    if not await Product.objects.filter(id=data.product_id, is_active=True).aexists():
        raise HttpError(404, "Товар недоступен")
    async with service.redis() as r:
        await service.add(r, request.auth.id, data.product_id, data.quantity)
        return await _render(r, request.auth.id)


@router.put("/items/{product_id}", response=CartOut)
@rate_limit(**WRITE_LIMIT)
async def set_item(request, product_id: int, data: SetQtyIn):
    if data.quantity > 0 and not await Product.objects.filter(id=product_id, is_active=True).aexists():
        raise HttpError(404, "Товар недоступен")
    async with service.redis() as r:
        await service.set_qty(r, request.auth.id, product_id, data.quantity)
        return await _render(r, request.auth.id)


@router.delete("/items/{product_id}", response=CartOut)
@rate_limit(**WRITE_LIMIT)
async def remove_item(request, product_id: int):
    async with service.redis() as r:
        await service.remove(r, request.auth.id, product_id)
        return await _render(r, request.auth.id)


@router.delete("", response=CartOut)
@rate_limit(**WRITE_LIMIT)
async def clear_cart(request):
    async with service.redis() as r:
        await service.clear(r, request.auth.id)
        return await _render(r, request.auth.id)
