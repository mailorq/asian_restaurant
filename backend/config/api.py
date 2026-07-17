from ninja import NinjaAPI, Schema

from accounts.api import router as auth_router

# django-ninja auto-enforces csrf once cookie/session auth is attached
api = NinjaAPI(title="Asian Restaurant API", version="1.0.0")


class HealthOut(Schema):
    status: str


@api.get("/health", response=HealthOut, auth=None, tags=["ops"])
def health(request) -> dict:
    return {"status": "ok"}


api.add_router("/auth", auth_router)