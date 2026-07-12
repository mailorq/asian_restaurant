from ninja import NinjaAPI, Schema

# session auth for a same-origin SPA requires CSRF
api = NinjaAPI(title="Asian Restaurant API", version="1.0.0", csrf=True)


class HealthOut(Schema):
    status: str


@api.get("/health", response=HealthOut, auth=None, tags=["ops"])
def health(request) -> dict:
    return {"status": "ok"}
