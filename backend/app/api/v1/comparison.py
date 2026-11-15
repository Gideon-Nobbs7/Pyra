"""GET /api/v1/comparison — selected period vs historical median.

The selected window's detection count is compared against the median count
for the same calendar window across prior years in the store, same bbox and
products. An anomaly is observed deviation from that baseline, never a
forecast. No percentages, no division by zero: the delta is absolute.
"""

import logging
import statistics
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db
from app.api.v1.observations import _fixture_page, _inside_fixture_coverage
from app.api.v1.query import parse_bbox, parse_dt, parse_products
from app.fixtures import FIXTURE_BBOX, FIXTURE_END, FIXTURE_START, get_freshness

router = APIRouter()
log = logging.getLogger("pyra.comparison")

BASELINE_YEARS = 10


def _error(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": {}}}, status_code=status
    )


COUNT_SQL = """
SELECT COUNT(*) AS n
FROM observations
WHERE observed_at >= %(start)s
  AND observed_at <= %(end)s
  AND longitude >= %(min_lon)s AND longitude <= %(max_lon)s
  AND latitude >= %(min_lat)s AND latitude <= %(max_lat)s
  AND source = ANY (%(products)s)
"""

BASELINE_SQL = """
SELECT EXTRACT(YEAR FROM observed_at)::int AS yr, COUNT(*) AS n
FROM observations
WHERE longitude >= %(min_lon)s AND longitude <= %(max_lon)s
  AND latitude >= %(min_lat)s AND latitude <= %(max_lat)s
  AND source = ANY (%(products)s)
  AND (
    (to_char(observed_at, 'MMDD') BETWEEN %(md_start)s AND %(md_end)s AND %(wrap)s = false)
    OR ((to_char(observed_at, 'MMDD') >= %(md_start)s OR to_char(observed_at, 'MMDD') <= %(md_end)s)
        AND %(wrap)s = true)
  )
  AND EXTRACT(YEAR FROM observed_at) BETWEEN %(year_lo)s AND %(year_hi)s
GROUP BY 1 ORDER BY 1
"""


def _direction(delta: int) -> str:
    if delta > 0:
        return "above"
    if delta < 0:
        return "below"
    return "at_baseline"


def _baseline_warning(base: str, counts: list[int]) -> str:
    """Name a missing baseline explicitly: median 0 with no sample years
    is not a baseline, and must never read as an anomaly anchor."""
    if counts:
        return base
    return (
        base + " No prior-year observations exist in the archive for this area and window, "
        "so no historical baseline could be computed."
    )


@router.get("/comparison")
async def comparison(request: Request) -> JSONResponse:
    params = dict(request.query_params)
    allowed = {"start", "end", "bbox", "limit", "cursor", "products"}
    unknown = sorted(set(params) - allowed)
    if unknown:
        return _error("invalid_params", f"unknown parameters: {', '.join(unknown)}", 422)

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

    def envelope(
        selected, baseline, anomaly, freshness, coverage_status, coverage_reason, synthetic, warning
    ):
        return JSONResponse(
            {
                "selected": selected,
                "baseline": baseline,
                "anomaly": anomaly,
                "filters": {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "bbox": bbox,
                    "products": products,
                },
                "filters_applied": {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "bbox": bbox,
                    "products": products,
                },
                "coverage": {
                    "start": start.isoformat() if coverage_status != "unavailable" else None,
                    "end": end.isoformat() if coverage_status != "unavailable" else None,
                    "available": coverage_status != "unavailable",
                },
                "freshness": {**freshness, "fetched_at": fetched_at},
                "coverage_status": coverage_status,
                "coverage_reason": coverage_reason,
                "comparability_warning": warning,
                "synthetic": synthetic,
            }
        )

    md_start = start.strftime("%m%d")
    md_end = end.strftime("%m%d")
    wrap = md_end < md_start
    warning = (
        "Selected period compared against the same calendar window in prior years, "
        "same area and products. Sensor coverage changes over time (MODIS from Nov 2000, "
        "VIIRS NOAA-20 from Apr 2018, NOAA-21 from Mar 2023), so cross-year counts are "
        "not strictly comparable. Never presented as a forecast or fire-risk score, "
        "and never as a percentage change from a zero baseline."
    )

    if db.db_configured():
        try:
            import psycopg
            import psycopg.rows

            url, _ = db.resolve_database_url()
            base = {
                "min_lon": min_lon,
                "max_lon": max_lon,
                "min_lat": min_lat,
                "max_lat": max_lat,
                "products": products,
            }
            with psycopg.connect(
                url, connect_timeout=3, prepare_threshold=None, row_factory=psycopg.rows.dict_row
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        COUNT_SQL, {**base, "start": start.isoformat(), "end": end.isoformat()}
                    )
                    selected_count = cur.fetchone()["n"]
                    cur.execute(
                        BASELINE_SQL,
                        {
                            **base,
                            "md_start": md_start,
                            "md_end": md_end,
                            "wrap": wrap,
                            "year_lo": end.year - BASELINE_YEARS,
                            "year_hi": end.year - 1,
                        },
                    )
                    yearly = [(r["yr"], r["n"]) for r in cur.fetchall()]
            freshness = db.fetch_freshness()
            counts = [n for _, n in yearly]
            median = int(statistics.median(counts)) if counts else 0
            delta = selected_count - median
            baseline_note = _baseline_warning(warning, counts)
            return envelope(
                {"start": start.isoformat(), "end": end.isoformat(), "count": selected_count},
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "median_count": median,
                    "years": len(counts),
                    "sample_years": [y for y, _ in yearly],
                },
                {"count_delta": delta, "direction": _direction(delta)},
                freshness,
                "ok" if selected_count or counts else "empty",
                "ok"
                if selected_count or counts
                else "No satellite hotspot detections were returned for this area and period. "
                "This does not prove that no fire occurred.",
                False,
                baseline_note,
            )
        except Exception as exc:
            log.warning("comparison database read failed: %s", exc)
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
            {"start": start.isoformat(), "end": end.isoformat(), "count": 0},
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "median_count": 0,
                "years": 0,
                "sample_years": [],
            },
            {"count_delta": 0, "direction": "at_baseline"},
            get_freshness(),
            "unavailable",
            "Requested area/period is outside the M1 synthetic fixture coverage. "
            "No FIRMS data loaded yet.",
            True,
            warning,
        )

    page, _, _ = _fixture_page(start, end, min_lon, min_lat, max_lon, max_lat, products, 100000, 0)
    selected_count = len(page)
    return envelope(
        {"start": start.isoformat(), "end": end.isoformat(), "count": selected_count},
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "median_count": 0,
            "years": 0,
            "sample_years": [],
        },
        {"count_delta": selected_count, "direction": _direction(selected_count)},
        get_freshness(),
        "ok" if page else "empty",
        "ok"
        if page
        else "No satellite hotspot detections were returned for this area and period. "
        "This does not prove that no fire occurred.",
        True,
        warning + " Synthetic fixtures cover a single month of a single year, "
        "so no historical baseline exists yet.",
    )
