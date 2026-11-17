"""GET /api/v1/summary: hotspot counts by day/month/year (same envelope as observations)."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db
from app.api.v1.observations import _fixture_page, _inside_fixture_coverage
from app.api.v1.query import parse_bbox, parse_dt, parse_products
from app.fixtures import FIXTURE_BBOX, FIXTURE_END, FIXTURE_START, get_freshness

router = APIRouter()
log = logging.getLogger("pyra.summary")

INTERVALS = ("day", "month", "year")


def _error(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": {}}}, status_code=status
    )


def _add_interval(start: datetime, interval: str) -> datetime:
    if interval == "day":
        if start.month == 12 and start.day == 31:
            return datetime(start.year + 1, 1, 1, tzinfo=UTC)
        import calendar as _cal

        month_days = _cal.monthrange(start.year, start.month)[1]
        if start.day < month_days:
            return start.replace(day=start.day + 1)
        if start.month < 12:
            return datetime(start.year, start.month + 1, 1, tzinfo=UTC)
        return datetime(start.year + 1, 1, 1, tzinfo=UTC)
    if interval == "month":
        if start.month < 12:
            return datetime(start.year, start.month + 1, 1, tzinfo=UTC)
        return datetime(start.year + 1, 1, 1, tzinfo=UTC)
    return datetime(start.year + 1, 1, 1, tzinfo=UTC)


def _floor_interval(value: datetime, interval: str) -> datetime:
    value = value.replace(tzinfo=UTC)
    if interval == "day":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "month":
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return value.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


BUCKET_SQL = """
SELECT date_trunc(%(interval)s, observed_at) AS bucket, COUNT(*) AS n
FROM observations
WHERE observed_at >= %(start)s
  AND observed_at <= %(end)s
  AND longitude >= %(min_lon)s AND longitude <= %(max_lon)s
  AND latitude >= %(min_lat)s AND latitude <= %(max_lat)s
  AND source = ANY (%(products)s)
GROUP BY 1 ORDER BY 1
"""


def _buckets_from_db(
    start_iso: str, end_iso: str, bbox: list[float], products: list[str], interval: str
) -> tuple[list[dict], int]:
    url, _ = db.resolve_database_url()
    params = {
        "interval": interval,
        "start": start_iso,
        "end": end_iso,
        "min_lon": bbox[0],
        "max_lon": bbox[2],
        "min_lat": bbox[1],
        "max_lat": bbox[3],
        "products": products,
    }
    with db._try_connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(BUCKET_SQL, params)
            rows = cur.fetchall()
    buckets = []
    total = 0
    for r in rows:
        b_start = r["bucket"]
        b_start = b_start.replace(tzinfo=UTC) if hasattr(b_start, "isoformat") else b_start
        b_end = _add_interval(b_start, interval)
        buckets.append({"start": b_start.isoformat(), "end": b_end.isoformat(), "count": r["n"]})
        total += r["n"]
    return buckets, total


@router.get("/summary")
async def summary(request: Request) -> JSONResponse:
    params = dict(request.query_params)
    allowed = {"start", "end", "bbox", "limit", "cursor", "products", "interval"}
    unknown = sorted(set(params) - allowed)
    if unknown:
        return _error("invalid_params", f"unknown parameters: {', '.join(unknown)}", 422)
    interval = (params.get("interval") or "month").strip().lower()
    if interval not in INTERVALS:
        return _error("invalid_params", f"interval must be one of {', '.join(INTERVALS)}", 422)

    try:
        start_raw = params.get("start", FIXTURE_START.isoformat())
        end_raw = params.get("end", FIXTURE_END.isoformat())
        bbox_raw = params.get("bbox", ",".join(map(str, FIXTURE_BBOX)))
        products_raw = params.get("products")
        start = parse_dt(start_raw, "start")
        end = parse_dt(end_raw, "end")
        if end < start:
            return _error("invalid_params", "end must be >= start", 422)
        min_lon, min_lat, max_lon, max_lat = parse_bbox(bbox_raw)
        products = parse_products(products_raw)
    except ValueError as exc:
        return _error("invalid_params", str(exc), 422)

    bbox = [min_lon, min_lat, max_lon, max_lat]
    fetched_at = datetime.now(UTC).isoformat()

    def envelope(data, count, freshness, coverage_status, coverage_reason, synthetic):
        return JSONResponse(
            {
                "data": data,
                "count": count,
                "filters": {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "bbox": bbox,
                    "products": products,
                    "interval": interval,
                },
                "filters_applied": {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "bbox": bbox,
                    "products": products,
                    "interval": interval,
                },
                "coverage": {
                    "start": start.isoformat() if coverage_status != "unavailable" else None,
                    "end": end.isoformat() if coverage_status != "unavailable" else None,
                    "available": coverage_status != "unavailable",
                },
                "freshness": {**freshness, "fetched_at": fetched_at},
                "coverage_status": coverage_status,
                "coverage_reason": coverage_reason,
                "synthetic": synthetic,
            }
        )

    if db.db_configured():
        try:
            buckets, total = _buckets_from_db(
                start.isoformat(), end.isoformat(), bbox, products, interval
            )
            freshness = db.fetch_freshness()
            status = "ok" if buckets else "empty"
            reason = (
                "ok"
                if buckets
                else "No satellite hotspot detections were returned for this area and period. "
                "This does not prove that no fire occurred."
            )
            return envelope(buckets, total, freshness, status, reason, False)
        except Exception as exc:
            log.warning("summary database read failed: %s", exc)
            return JSONResponse(
                {
                    "error": {
                        "code": "upstream_unavailable",
                        "message": "The observation store is unreachable. Retry shortly; "
                        "no result is implied by this response.",
                        "details": {},
                    }
                },
                status_code=503,
            )

    if not _inside_fixture_coverage(start, end, min_lon, min_lat, max_lon, max_lat):
        return envelope(
            [],
            0,
            get_freshness(),
            "unavailable",
            "Requested area/period is outside the M1 synthetic fixture coverage. "
            "No FIRMS data loaded yet.",
            True,
        )

    from collections import defaultdict

    page, _, _ = _fixture_page(start, end, min_lon, min_lat, max_lon, max_lat, products, 100000, 0)
    counts: dict[str, int] = defaultdict(int)
    for r in page:
        obs = parse_dt(r["observed_at"], "observed_at")
        key = _floor_interval(obs, interval).isoformat()
        counts[key] += 1
    buckets = [
        {"start": k, "end": _add_interval(parse_dt(k, "k"), interval).isoformat(), "count": v}
        for k, v in sorted(counts.items())
    ]
    status = "ok" if buckets else "empty"
    reason = (
        "ok"
        if buckets
        else "No satellite hotspot detections were returned for this area and period. "
        "This does not prove that no fire occurred."
    )
    return envelope(buckets, sum(counts.values()), get_freshness(), status, reason, True)
