import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()
log = logging.getLogger("pyra.places")

PHOTON_HOST = "photon.komoot.io"
PHOTON_URL = f"https://{PHOTON_HOST}/api/"

_client: httpx.AsyncClient | None = None


def _shared_client() -> httpx.AsyncClient:
    """Pooled keep-alive client. One TLS handshake, then sub-second repeats."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=3.0),
            headers={"User-Agent": "Pyra/0.1"},
        )
    return _client


async def close_client() -> None:
    """Lifespan shutdown hook. Safe to call when never started."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _fetch(params: dict) -> httpx.Response:
    return await _shared_client().get(PHOTON_URL, params=params)


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": {}}},
        status_code=status,
    )


def _slim_features(payload: object) -> list[dict] | None:
    """Validate the Photon shape and slim to name/city/state/country/latlon."""
    if not isinstance(payload, dict):
        return None
    features = payload.get("features")
    if not isinstance(features, list):
        return None
    slimmed = []
    for feature in features:
        if not isinstance(feature, dict):
            return None
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        if not isinstance(geometry, dict) or not isinstance(properties, dict):
            return None
        coordinates = geometry.get("coordinates")
        if (
            not isinstance(coordinates, list)
            or len(coordinates) < 2
            or not isinstance(coordinates[0], (int, float))
            or not isinstance(coordinates[1], (int, float))
        ):
            return None
        slimmed.append(
            {
                "name": properties.get("name"),
                "city": properties.get("city"),
                "state": properties.get("state"),
                "country": properties.get("country"),
                "latitude": coordinates[1],
                "longitude": coordinates[0],
            }
        )
    return slimmed


@router.get("/places")
async def search_places(request: Request) -> JSONResponse:
    params = dict(request.query_params)
    allowed = {"q", "limit", "lang"}
    unknown = sorted(set(params) - allowed)
    if unknown:
        return _error("invalid_params", f"unknown parameters: {', '.join(unknown)}", 422)

    query = (params.get("q") or "").strip()
    if len(query) < 2 or len(query) > 200:
        return _error("invalid_params", "q must be 2..200 characters", 422)
    try:
        limit = int(params.get("limit", "6"))
    except ValueError:
        return _error("invalid_params", "limit must be an integer in [1, 10]", 422)
    if not 1 <= limit <= 10:
        return _error("invalid_params", "limit must be an integer in [1, 10]", 422)
    lang = (params.get("lang") or "en").strip().lower()
    if not (len(lang) == 2 and lang.isalpha()):
        return _error("invalid_params", "lang must be a 2-letter code", 422)

    try:
        response = await _fetch({"q": query, "limit": str(limit), "lang": lang})
    except Exception as exc:
        log.warning("place search provider unreachable: %s", exc)
        return _error(
            "upstream_unavailable",
            "Place search is temporarily unavailable. Retry shortly; "
            "no result is implied by this response.",
            503,
        )
    if response.status_code != 200:
        log.warning("place search provider returned HTTP %s", response.status_code)
        return _error(
            "upstream_unavailable",
            "Place search is temporarily unavailable. Retry shortly; "
            "no result is implied by this response.",
            503,
        )
    try:
        slimmed = _slim_features(response.json())
    except ValueError:
        slimmed = None
    if slimmed is None:
        log.warning("place search returned an invalid response shape")
        return _error(
            "upstream_unavailable",
            "Place search returned an invalid response. Retry shortly; "
            "no result is implied by this response.",
            503,
        )
    return JSONResponse({"data": slimmed})
