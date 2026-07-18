from ninja import NinjaAPI, Schema

from accounts.api import router as auth_router
from cart.api import router as cart_router

# swagger ui served at /api/docs, openapi schema at /api/openapi.json (fastapi-style)
api = NinjaAPI(
    title="Asian Restaurant API",
    version="1.0.0",
    description="OpenAPI. Auth, Cart ...",
    docs_url="/docs",
)


class HealthOut(Schema):
    status: str


@api.get("/health", response=HealthOut, auth=None, tags=["ops"])
def health(request) -> dict:
    return {"status": "ok"}


api.add_router("/auth", auth_router)
api.add_router("/cart", cart_router)
