import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings

from orders.models import GeocodeCache


class GeocoderUnavailable(Exception):
    """The external geocoder could not be reached for an uncached query."""


@dataclass
class GeocodeResult:
    found: bool
    lat: float | None = None
    lng: float | None = None
    display_name: str = ""


def _normalize(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _key(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class GeocoderProvider:
    def geocode(self, query: str) -> GeocodeResult:  # pragma: no cover - interface
        raise NotImplementedError


class NominatimProvider(GeocoderProvider):
    def geocode(self, query: str) -> GeocodeResult:
        params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
        request = urllib.request.Request(
            f"{settings.GEOCODER_URL}?{params}",
            headers={"User-Agent": settings.GEOCODER_USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=settings.GEOCODER_TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise GeocoderUnavailable(str(exc)) from exc
        if not payload:
            return GeocodeResult(found=False)
        top = payload[0]
        return GeocodeResult(
            found=True,
            lat=float(top["lat"]),
            lng=float(top["lon"]),
            display_name=top.get("display_name", ""),
        )


def get_provider() -> GeocoderProvider:
    return NominatimProvider()


def geocode(query: str) -> GeocodeResult:
    """Verify/geocode an address, consulting the cache before the provider"""
    normalized = _normalize(query)
    if not normalized:
        return GeocodeResult(found=False)

    key = _key(normalized)
    cached = GeocodeCache.objects.filter(query_hash=key).first()
    if cached is not None:
        return GeocodeResult(
            found=cached.found,
            lat=float(cached.lat) if cached.lat is not None else None,
            lng=float(cached.lng) if cached.lng is not None else None,
            display_name=cached.display_name,
        )

    if not settings.GEOCODER_ENABLED:
        raise GeocoderUnavailable("geocoder disabled")

    result = get_provider().geocode(normalized)  # may raise GeocoderUnavailable
    GeocodeCache.objects.update_or_create(
        query_hash=key,
        defaults={
            "query": normalized[:500],
            "found": result.found,
            "lat": result.lat,
            "lng": result.lng,
            "display_name": (result.display_name or "")[:500],
            "provider": "nominatim",
        },
    )
    return result
