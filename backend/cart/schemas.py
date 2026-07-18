from ninja import Field, Schema


class AddItemIn(Schema):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=50)


class SetQtyIn(Schema):
    quantity: int = Field(ge=0, le=50)


class CartLineOut(Schema):
    product_id: int
    name: str
    price: float
    quantity: int
    image: str | None = None
    available: bool


class CartOut(Schema):
    items: list[CartLineOut]
    total: float
    count: int
