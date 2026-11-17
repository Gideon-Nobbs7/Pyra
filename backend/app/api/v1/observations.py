"""GET /api/v1/observations: validated time+area query, Postgres first, fixtures fallback."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db, firms, ingest_jobs
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
    """Live FIRMS pull on DB miss, warms Postgres for re-read."""
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


async def _live_observations(
    start,
    end,
    min_lon,
    min_lat,
    max_lon,
    max_lat,
    bbox_raw: str,
    products: list[str],
    limit: int,
    offset: int,
) -> JSONResponse:
    """Live FIRMS read: no cache/DB/upsert. Single-flight per identical request."""
    bbox = [min_lon, min_lat, max_lon, max_lat]
    window = firms.on_demand_window(start, end, bbox)
    if window is None:
        now = datetime.now(UTC)
        if end < now - timedelta(days=firms.ON_DEMAND_LOOKBACK_DAYS):
            reason = (
                "Live fetch covers the recent window only. For older periods, "
                "run an ingest or wait for the archive backfill."
            )
        else:
            reason = (
                "Live fetch is bounded to "
                f"{firms.ON_DEMAND_MAX_DEG2:g} deg\u00b2. Lock a smaller area "
                "or run an ingest for wide areas."
            )
        return JSONResponse(
            _envelope(
                data=[],
                count=0,
                limit=limit,
                next_cursor=None,
                has_more=False,
                start_iso=start.isoformat(),
                end_iso=end.isoformat(),
                bbox_list=bbox,
                products=products,
                freshness={
                    "latest_ingested_at": None,
                    "row_count": 0,
                    "synthetic": False,
                    "store": "live",
                    "note": "live FIRMS pull; not stored",
                },
                coverage_status="unavailable",
                coverage_reason=reason,
                synthetic=False,
            )
        )
    if not firms.map_key():
        return _error(
            "upstream_unavailable",
            "Live mode requires FIRMS_MAP_KEY on the server.",
            status=503,
        )
    if not firms.rate_limit_ok():
        return _error(
            "rate_limited",
            "Live fetch throttled to protect the shared FIRMS quota. Retry in about a minute.",
            status=429,
        )
    try:
        api_products = firms.load_api_products()
    except ValueError as exc:
        log.error("live fetch skipped, bad FIRMS_API_PRODUCTS: %s", exc)
        return _error("upstream_unavailable", f"bad FIRMS_API_PRODUCTS: {exc}", status=503)
    _, fetch_end, _ = window
    lock_key = cache_state.cache.make_key(
        ",".join(products), start.isoformat(), end.isoformat(), bbox_raw, limit, ""
    )
    async with cache_state.cache.lock_for("live:" + lock_key):
        try:
            records, failures = firms.fetch_live_records(
                api_products, products, bbox, fetch_end, timeout_s=8
            )
        except Exception as exc:
            log.warning("live fetch failed: %s", exc)
            return _error(
                "upstream_unavailable",
                "The live FIRMS request failed. Retry shortly; "
                "no result is implied by this response.",
                status=503,
            )
    if failures:
        log.info("live fetch partial failures: %s", failures)
    if not records and failures:
        return _error(
            "upstream_unavailable",
            "The live FIRMS request failed. Retry shortly; no result is implied by this response.",
            status=503,
        )
    records.sort(key=lambda r: (r["observed_at"], r["id"]))
    total = len(records)
    page_raw = records[offset : offset + limit]
    has_more = offset + len(page_raw) < total
    page = [db._row_to_record(r) for r in page_raw]
    status = "ok" if page else "empty"
    fetched_at = datetime.now(UTC).isoformat()
    return JSONResponse(
        _envelope(
            data=page,
            count=total,
            limit=limit,
            next_cursor=encode_cursor(offset + len(page)) if has_more else None,
            has_more=has_more,
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
            bbox_list=bbox,
            products=products,
            freshness={
                "latest_ingested_at": fetched_at,
                "row_count": total,
                "synthetic": False,
                "store": "live",
                "note": "live FIRMS pull; not stored",
            },
            coverage_status=status,
            coverage_reason=(
                "ok"
                if page
                else "No satellite hotspot detections were returned for this area "
                "and period. This does not prove that no fire occurred."
            ),
            synthetic=False,
        )
    )


def _enqueue_gap_fill(start, end, bbox: list[float]) -> None:
    """Best-effort gap-fill enqueue (history/wide windows only)."""
    try:
        if firms.on_demand_window(start, end, bbox) is not None:
            return
        outcome = ingest_jobs.enqueue_job(bbox, start, end)
        log.info(
            "gap-fill %s bbox=%s window=%s..%s",
            outcome,
            bbox,
            start.date(),
            end.date(),
        )
    except Exception as exc:
        log.warning("gap-fill enqueue failed: %s", exc)


def _inside_fixture_coverage(start, end, min_lon, min_lat, max_lon, max_lat) -> bool:
    """True inside the labelled M1 fixture window."""
    time_outside = end < FIXTURE_START or start > FIXTURE_END
    area_outside = (max_lon < FIXTURE_BBOX[0] or min_lon > FIXTURE_BBOX[2]) or (
        max_lat < FIXTURE_BBOX[1] or min_lat > FIXTURE_BBOX[3]
    )
    return not (time_outside or area_outside)


def _fixture_page(start, end, min_lon, min_lat, max_lon, max_lat, products, limit, offset):
    """Filter fixtures by time+area. Returns (page, has_more, total)."""
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
    return page, offset + len(page) < len(kept), len(kept)


def _envelope(
    *,
    data,
    count,
    limit,
    next_cursor,
    has_more,
    start_iso,
    end_iso,
    bbox_list,
    products,
    freshness,
    coverage_status,
    coverage_reason,
    synthetic,
):
    """Shared response envelope: data + state, freshness, provenance."""
    available = coverage_status != "unavailable"
    filters = {"start": start_iso, "end": end_iso, "bbox": bbox_list, "products": products}
    return {
        "data": data,
        "count": count,
        "filters": filters,
        "filters_applied": dict(filters),
        "coverage": {
            "start": start_iso if available else None,
            "end": end_iso if available else None,
            "available": available,
        },
        "freshness": {**freshness, "fetched_at": datetime.now(UTC).isoformat()},
        "pagination": {
            "limit": limit,
            "next_cursor": next_cursor,
            "cursor_next": next_cursor,
            "has_more": has_more,
        },
        "coverage_status": coverage_status,
        "coverage_reason": coverage_reason,
        "synthetic": synthetic,
    }


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
        live_raw = (params.get("live") or "").strip().lower()
        if live_raw and live_raw not in ("1", "true"):
            return _error("invalid_params", "live must be '1' or 'true' when present", status=422)
        live = live_raw in ("1", "true")
    except ValueError as exc:
        return _error("invalid_params", str(exc), status=422)
    except Exception:
        return _error("invalid limit; must be an integer", status=422)

    if live:
        return await _live_observations(
            start, end, min_lon, min_lat, max_lon, max_lat, bbox_raw, products, limit, offset
        )

    # Fixture-only coverage gate.
    if not db.db_configured():
        if not _inside_fixture_coverage(start, end, min_lon, min_lat, max_lon, max_lat):
            return JSONResponse(
                _envelope(
                    data=[],
                    count=0,
                    limit=limit,
                    next_cursor=None,
                    has_more=False,
                    start_iso=start.isoformat(),
                    end_iso=end.isoformat(),
                    bbox_list=[min_lon, min_lat, max_lon, max_lat],
                    products=products,
                    freshness=get_freshness(),
                    coverage_status="unavailable",
                    coverage_reason=(
                        "Requested area/period is outside the M1 synthetic fixture coverage "
                        f"(bbox {list(FIXTURE_BBOX)}, "
                        f"{FIXTURE_START.date()}..{FIXTURE_END.date()}). "
                        "No FIRMS data loaded yet."
                    ),
                    synthetic=True,
                )
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
                    # DB miss: bounded live pull, then re-read.
                    page, has_more = _maybe_on_demand_fetch(
                        start, end, [min_lon, min_lat, max_lon, max_lat], products, limit, offset
                    )
                    if not page:
                        _enqueue_gap_fill(start, end, [min_lon, min_lat, max_lon, max_lat])
                from_fixtures = False
                total = 0
                if not page and _inside_fixture_coverage(
                    start, end, min_lon, min_lat, max_lon, max_lat
                ):
                    # No stored rows yet: labelled fixtures cover the demo window.
                    page, has_more, total = _fixture_page(
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
                if not from_fixtures:
                    total = db.fetch_count(
                        start.isoformat(),
                        end.isoformat(),
                        [min_lon, min_lat, max_lon, max_lat],
                        products,
                    )
                freshness = get_freshness() if from_fixtures else db.fetch_freshness()
                status = "ok" if page else "empty"
                body = _envelope(
                    data=page,
                    count=total,
                    limit=limit,
                    next_cursor=encode_cursor(offset + len(page)) if has_more else None,
                    has_more=has_more,
                    start_iso=start.isoformat(),
                    end_iso=end.isoformat(),
                    bbox_list=[min_lon, min_lat, max_lon, max_lat],
                    products=products,
                    freshness=freshness,
                    coverage_status=status,
                    coverage_reason=(
                        "ok"
                        if page
                        else "No satellite hotspot detections were returned for this area "
                        "and period. This does not prove that no fire occurred."
                    ),
                    synthetic=from_fixtures,
                )
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

        page, has_more, total = _fixture_page(
            start, end, min_lon, min_lat, max_lon, max_lat, products, limit, offset
        )
        status = "ok" if page else "empty"
        body = _envelope(
            data=page,
            count=total,
            limit=limit,
            next_cursor=encode_cursor(offset + len(page)) if has_more else None,
            has_more=has_more,
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
            bbox_list=[min_lon, min_lat, max_lon, max_lat],
            products=products,
            freshness=get_freshness(),
            coverage_status=status,
            coverage_reason=(
                "ok"
                if page
                else "No satellite hotspot detections were returned for this area and period. "
                "This does not prove that no fire occurred."
            ),
            synthetic=True,
        )
        ttl = cache_state.cache.ttl_for(start.isoformat(), end.isoformat())
        cache_state.cache.put(key, body, ttl)
        log.info("cache miss key=%s ttl=%s rows=%d", key, ttl, len(page))
        return JSONResponse(body)
