from ninja import Router
from ninja.errors import HttpError

from menu.models import Product
from menu.schemas import ProductOut

router = Router(tags=["menu"])


def _active():
    return Product.objects.filter(is_active=True).prefetch_related("ingredients")


@router.get("/products", response=list[ProductOut], auth=None)
def list_products(request, category: str | None = None):
    qs = _active()
    if category:
        qs = qs.filter(category=category)
    return list(qs)


@router.get("/products/{id_or_code}", response=ProductOut, auth=None)
def get_product(request, id_or_code: str):
    qs = _active()
    try:
        pk = int(id_or_code)
    except ValueError:
        pk = None
    product = qs.filter(id=pk).first() if pk is not None else qs.filter(code=id_or_code).first()
    if product is None:
        raise HttpError(404, "Товар не найден")
    return product
