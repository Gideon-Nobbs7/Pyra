"""DB layer: tiered stores with automatic failover.

Chain (first reachable wins, sticky for RESOLUTION_TTL_S):
  1. DATABASE_URL          primary  (Cloud SQL managed Postgres+PostGIS)
  2. DATABASE_URL_FALLBACK fallback (Supabase)
  3. DATABASE_URL_LOCAL    local    (Compose PostGIS, offline use)

Freshness always names the store that answered, so fallback data is never
presented as equally fresh. Fixtures serve only when no store is configured
(fixture mode) — a configured-but-unreachable chain is a 503, never a silent
empty.
"""

import os
import time

DATABASE_URL = os.getenv("DATABASE_URL", "")
FALLBACK_URL = os.getenv("DATABASE_URL_FALLBACK", "")
LOCAL_URL = os.getenv("DATABASE_URL_LOCAL", "")
USE_DB = bool(DATABASE_URL or FALLBACK_URL or LOCAL_URL)

RESOLUTION_TTL_S = 60.0

_ACTIVE: dict = {"url": None, "role": None, "ts": 0.0}

# Parameterized query used once DB is wired. No string concatenation.
OBSERVATIONS_SQL = """
SELECT id, source, source_record_id, observed_at, ingested_at,
       latitude, longitude,
       instrument, platform, confidence, frp, frp_unit,
       quality_flags, product_version, raw_properties
FROM observations
WHERE observed_at >= %(start)s
  AND observed_at < %(end)s
  AND longitude >= %(min_lon)s AND longitude <= %(max_lon)s
  AND latitude >= %(min_lat)s AND latitude <= %(max_lat)s
  AND (%(products)s = '' OR source = ANY (string_to_array(%(products)s, ',')))
ORDER BY observed_at ASC, id ASC
LIMIT %(limit)s
"""

DB_PAGE_SQL = """
SELECT id, source, source_record_id, observed_at, ingested_at,
       latitude, longitude,
       instrument, platform, confidence, frp, frp_unit,
       quality_flags, product_version, raw_properties
FROM observations
WHERE observed_at >= %(start)s
  AND observed_at <= %(end)s
  AND longitude >= %(min_lon)s AND longitude <= %(max_lon)s
  AND latitude >= %(min_lat)s AND latitude <= %(max_lat)s
  AND source = ANY (%(products)s)
ORDER BY observed_at ASC, id ASC
LIMIT %(limit)s OFFSET %(offset)s
"""

DB_FRESHNESS_SQL = "SELECT max(ingested_at) AS latest, count(*) AS n FROM observations"


def db_configured() -> bool:
    # Dynamic (not import-time) so tests and process env changes take effect.
    return bool(os.getenv("DATABASE_URL", "") or os.getenv("DATABASE_URL_FALLBACK", ""))


def db_status() -> str:
    if not USE_DB:
        return "not_configured"
    return "configured"


def reset_resolution() -> None:
    """Tests only: forget the sticky primary/fallback decision."""
    _ACTIVE.update({"url": None, "role": None, "ts": 0.0})


def _try_connect(url: str, timeout: int = 3):
    import psycopg
    import psycopg.rows

    # prepare_threshold=None: no server-side prepared statements, so the
    # connection also works through Supavisor/pgbouncer transaction pooling.
    return psycopg.connect(
        url, connect_timeout=timeout, row_factory=psycopg.rows.dict_row, prepare_threshold=None
    )


def resolve_database_url() -> tuple[str, str]:
    """Return (url, role). Cloud SQL, then Supabase, then local. Raises on total failure."""
    now = time.monotonic()
    if _ACTIVE["url"] and now - _ACTIVE["ts"] < RESOLUTION_TTL_S:
        return _ACTIVE["url"], _ACTIVE["role"]
    candidates = []
    if DATABASE_URL:
        candidates.append((DATABASE_URL, "primary"))
    if FALLBACK_URL:
        candidates.append((FALLBACK_URL, "fallback"))
    if LOCAL_URL:
        candidates.append((LOCAL_URL, "local"))
    if not candidates:
        raise ConnectionError("no database configured")
    last_exc: Exception | None = None
    for url, role in candidates:
        try:
            conn = _try_connect(url)
            conn.close()
            _ACTIVE.update({"url": url, "role": role, "ts": now})
            return url, role
        except Exception as exc:  # noqa: BLE001 (probe next candidate, log at call site)
            last_exc = exc
            continue
    raise ConnectionError(f"all database stores unreachable: {last_exc}")


def _row_to_record(row: dict) -> dict:
    raw_props = row.get("raw_properties")
    if isinstance(raw_props, str):
        import json

        try:
            raw_props = json.loads(raw_props)
        except ValueError:
            raw_props = {"value": raw_props}
    record = dict(row)
    for key in ("observed_at", "ingested_at"):
        value = record.get(key)
        if hasattr(value, "isoformat"):
            record[key] = value.isoformat()
    record["raw_properties"] = raw_props
    return record


def fetch_page(
    start_iso: str, end_iso: str, bbox: list[float], products: list[str], limit: int, offset: int
) -> tuple[list[dict], bool]:
    """Query one page plus one lookahead row. Raises on DB failure."""
    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "start": start_iso,
        "end": end_iso,
        "min_lon": min_lon,
        "max_lon": max_lon,
        "min_lat": min_lat,
        "max_lat": max_lat,
        "products": products,
        "limit": limit + 1,
        "offset": offset,
    }
    url, _ = resolve_database_url()
    with _try_connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(DB_PAGE_SQL, params)
            rows = cur.fetchall()
    records = [_row_to_record(r) for r in rows]
    has_more = len(records) > limit
    return records[:limit], has_more


def fetch_freshness() -> dict:
    """Freshness from the latest successful ingestion. Names the store. Raises on failure."""
    url, role = resolve_database_url()
    with _try_connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(DB_FRESHNESS_SQL)
            row = cur.fetchone()
    latest = row["latest"] if row else None
    return {
        "latest_ingested_at": latest.isoformat() if hasattr(latest, "isoformat") else None,
        "row_count": row["n"] if row else 0,
        "synthetic": False,
        "store": role,
        "note": f"latest successful FIRMS ingestion into Postgres ({role})",
    }
