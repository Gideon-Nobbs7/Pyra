import base64
from datetime import UTC, datetime

ALLOWED_PARAMS = {"start", "end", "bbox", "limit", "cursor", "products", "live"}


def reject_unknown(params: dict) -> str | None:
    unknown = sorted(set(params) - ALLOWED_PARAMS)
    if unknown:
        return f"unknown parameters: {', '.join(unknown)}"
    return None


def parse_dt(value: str, name: str) -> datetime:
    try:
        text = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    except Exception as exc:
        raise ValueError(f"{name} must be ISO-8601 UTC, got {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        parts = [float(p.strip()) for p in value.split(",")]
    except Exception as exc:
        raise ValueError(f"bbox must be min_lon,min_lat,max_lon,max_lat, got {value!r}") from exc
    if len(parts) != 4:
        raise ValueError(f"bbox must have 4 numbers, got {value!r}")
    min_lon, min_lat, max_lon, max_lat = parts
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise ValueError("bbox longitudes must be in [-180, 180]")
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise ValueError("bbox latitudes must be in [-90, 90]")
    if not (min_lon < max_lon and min_lat < max_lat):
        raise ValueError("bbox must satisfy min_lon < max_lon and min_lat < max_lat")
    return min_lon, min_lat, max_lon, max_lat


def parse_products(value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return ["modis", "viirs"]
    items = [p.strip().lower() for p in value.split(",") if p.strip()]
    for p in items:
        if p not in ("modis", "viirs"):
            raise ValueError(f"products must be subset of modis,viirs, got {value!r}")
    return sorted(set(items))


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_cursor(value: str | None) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(base64.urlsafe_b64decode(value.encode()).decode())
    except Exception as exc:
        raise ValueError(f"cursor is opaque and invalid: {value!r}") from exc
