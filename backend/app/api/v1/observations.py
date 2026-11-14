"""GET /api/v1/observations (FIRMS-backed with fixture fallback).

Strict validation, time + area applied together, opaque cursor, explicit
empty vs unavailable. When DATABASE_URL is set, Postgres is the source of
truth; fixtures serve only if the database is unreachable (logged) or not
configured. Fixture mode keeps the narrow Attica/Aug-2024 coverage gate;
DB mode treats zero matches as empty.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db, firms
from app.api.v1.query import (
    decode_cursor,
    encode_cursor,
    parse_bbox,
    parse_dt,
    parse_products,
    reject_unknown,
)
from app.cache import cache_state
from app.fixtures import FIXTURE_BBOX, FIXTURE_END, FIXTURE_START, get_freshness, load_fixtures

router = APIRouter()
log = logging.getLogger("pyra.observations")


def _error(code: str, message: str, details: dict | None = None, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status_code=status,
    )


def _bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _maybe_on_demand_fetch(
    start, end, bbox: list[float], products: list[str], limit: int, offset: int
) -> tuple[list, bool]:
    """Bounded live FIRMS pull on a DB miss. Warms Postgres; caller re-reads."""
    if not firms.map_key():
        return [], False
    window = firms.on_demand_window(start, end, bbox)
    if window is None:
        return [], False  # historical or too-wide: the archive ingest's job
    if not firms.rate_limit_ok():
        log.info("on-demand fetch rate-limited; serving stored result")
        return [], False
    _, fetch_end, _ = window
    try:
        api_products = firms.load_api_products()
    except ValueError as exc:
        log.error("on-demand fetch skipped, bad FIRMS_API_PRODUCTS: %s", exc)
        return [], False
    try:
        active_url, _ = db.resolve_database_url()
    except Exception as exc:
        log.warning("no database store reachable for on-demand fetch: %s", exc)
        return [], False
    try:
        n, failures = firms.fetch_and_store(api_products, products, bbox, fetch_end, active_url)
    except Exception as exc:
        log.warning("on-demand fetch failed: %s", exc)
        return [], False
    if failures:
        log.warning("on-demand fetch partial failures: %s", failures)
    if n == 0:
        return [], False
    try:
        log.info("on-demand fetch stored %d rows; re-reading", n)
        return db.fetch_page(start.isoformat(), end.isoformat(), bbox, products, limit, offset)
    except Exception as exc:
        log.warning("database re-read failed after on-demand fetch: %s", exc)
        return [], False


def _inside_fixture_coverage(start, end, min_lon, min_lat, max_lon, max_lat) -> bool:
    """True when the query falls inside the labelled M1 fixture window."""
    time_outside = end < FIXTURE_START or start > FIXTURE_END
    area_outside = (max_lon < FIXTURE_BBOX[0] or min_lon > FIXTURE_BBOX[2]) or (
        max_lat < FIXTURE_BBOX[1] or min_lat > FIXTURE_BBOX[3]
    )
    return not (time_outside or area_outside)


def _fixture_page(start, end, min_lon, min_lat, max_lon, max_lat, products, limit, offset):
    """Filter the synthetic fixtures by time + area. Returns (page, has_more)."""
    records = load_fixtures()
    kept = []
    for r in records:
        if r["source"] not in products:
            continue
        try:
            obs = parse_dt(r["observed_at"], "observed_at")
        except ValueError:
            continue
        if not (start <= obs <= end):
            continue
        if not (min_lon <= r["longitude"] <= max_lon and min_lat <= r["latitude"] <= max_lat):
            continue
        kept.append(r)
    kept.sort(key=lambda r: (r["observed_at"], r["id"]))
    page = kept[offset : offset + limit]
    return page, offset + len(page) < len(kept)


@router.get("/observations")
async def list_observations(request: Request) -> JSONResponse:
    params = dict(request.query_params)
    unknown = reject_unknown(params)
    if unknown:
        return _error("invalid_params", unknown, status=422)

    try:
        start_raw = params.get("start", FIXTURE_START.isoformat())
        end_raw = params.get("end", FIXTURE_END.isoformat())
        bbox_raw = params.get("bbox", ",".join(map(str, FIXTURE_BBOX)))
        limit_raw = params.get("limit", "100")
        cursor_raw = params.get("cursor")
        products_raw = params.get("products")

        start = parse_dt(start_raw, "start")
        end = parse_dt(end_raw, "end")
        if end < start:
            return _error("invalid_params", "end must be >= start", status=422)
        min_lon, min_lat, max_lon, max_lat = parse_bbox(bbox_raw)
        limit = int(limit_raw)
        if not 1 <= limit <= 1000:
            return _error("invalid_params", "limit must be in [1, 1000]", status=422)
        offset = decode_cursor(cursor_raw)
        products = parse_products(products_raw)
    except ValueError as exc:
        return _error("invalid_params", str(exc), status=422)
    except Exception:
        return _error("invalid_params", "invalid limit; must be an integer", status=422)

    # Coverage gate applies to fixture-only mode (no DB configured).
    if not db.db_configured():
        if not _inside_fixture_coverage(start, end, min_lon, min_lat, max_lon, max_lat):
            return JSONResponse(
                {
                    "data": [],
                    "pagination": {"limit": limit, "cursor_next": None, "has_more": False},
                    "filters_applied": {
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "bbox": [min_lon, min_lat, max_lon, max_lat],
                        "products": products,
                    },
                    "freshness": get_freshness(),
                    "coverage_status": "unavailable",
                    "coverage_reason": (
                        "Requested area/period is outside the M1 synthetic fixture coverage "
                        f"(bbox {list(FIXTURE_BBOX)}, "
                        f"{FIXTURE_START.date()}..{FIXTURE_END.date()}). "
                        "No FIRMS data loaded yet."
                    ),
                    "synthetic": True,
                }
            )

    products_key = ",".join(products)
    key = cache_state.cache.make_key(
        products_key, start.isoformat(), end.isoformat(), bbox_raw, limit, cursor_raw or ""
    )
    cached = cache_state.cache.get(key)
    if cached is not None:
        log.info("cache hit key=%s", key)
        return JSONResponse(cached)

    async with cache_state.cache.lock_for(key):
        cached = cache_state.cache.get(key)
        if cached is not None:
            return JSONResponse(cached)

        if db.db_configured():
            try:
                page, has_more = db.fetch_page(
                    start.isoformat(),
                    end.isoformat(),
                    [min_lon, min_lat, max_lon, max_lat],
                    products,
                    limit,
                    offset,
                )
                if not page:
                    # Cache + DB miss: bounded live pull warms Postgres, then re-read.
                    page, has_more = _maybe_on_demand_fetch(
                        start, end, [min_lon, min_lat, max_lon, max_lat], products, limit, offset
                    )
                from_fixtures = False
                if not page and _inside_fixture_coverage(
                    start, end, min_lon, min_lat, max_lon, max_lat
                ):
                    # No source-backed rows here yet: labelled fixtures keep the
                    # demo window working until archive ingest covers it.
                    page, has_more = _fixture_page(
                        start,
                        end,
                        min_lon,
                        min_lat,
                        max_lon,
                        max_lat,
                        products,
                        limit,
                        offset,
                    )
                    from_fixtures = True
                    log.info("fixture fallback key=%s rows=%d", key, len(page))
                freshness = get_freshness() if from_fixtures else db.fetch_freshness()
                body = {
                    "data": page,
                    "pagination": {
                        "limit": limit,
                        "cursor_next": encode_cursor(offset + len(page)) if has_more else None,
                        "has_more": has_more,
                    },
                    "filters_applied": {
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "bbox": [min_lon, min_lat, max_lon, max_lat],
                        "products": products,
                    },
                    "freshness": freshness,
                    "coverage_status": "ok" if page else "empty",
                    "coverage_reason": (
                        "ok"
                        if page
                        else "No satellite hotspot detections were returned for this area "
                        "and period. This does not prove that no fire occurred."
                    ),
                    "synthetic": from_fixtures,
                }
                ttl = cache_state.cache.ttl_for(start.isoformat(), end.isoformat())
                cache_state.cache.put(key, body, ttl)
                log.info(
                    "db hit key=%s ttl=%s rows=%d synthetic=%s", key, ttl, len(page), from_fixtures
                )
                return JSONResponse(body)
            except Exception as exc:
                log.warning("database read failed: %s", exc)
                return _error(
                    "upstream_unavailable",
                    "The observation store is unreachable. Retry shortly; "
                    "no result is implied by this response.",
                    status=503,
                )

        page, has_more = _fixture_page(
            start, end, min_lon, min_lat, max_lon, max_lat, products, limit, offset
        )
        body = {
            "data": page,
            "pagination": {
                "limit": limit,
                "cursor_next": encode_cursor(offset + len(page)) if has_more else None,
                "has_more": has_more,
            },
            "filters_applied": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "bbox": [min_lon, min_lat, max_lon, max_lat],
                "products": products,
            },
            "freshness": get_freshness(),
            "coverage_status": "ok" if page else "empty",
            "coverage_reason": (
                "ok"
                if page
                else "No satellite hotspot detections were returned for this area and period. "
                "This does not prove that no fire occurred."
            ),
            "synthetic": True,
        }
        ttl = cache_state.cache.ttl_for(start.isoformat(), end.isoformat())
        cache_state.cache.put(key, body, ttl)
        log.info("cache miss key=%s ttl=%s rows=%d", key, ttl, len(page))
        return JSONResponse(body)
