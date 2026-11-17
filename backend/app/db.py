import threading
import time

from app.settings import get_settings

_settings = get_settings()
DATABASE_URL = _settings.database_url
FALLBACK_URL = _settings.database_url_fallback
LOCAL_URL = _settings.database_url_local
USE_DB = bool(DATABASE_URL or FALLBACK_URL or LOCAL_URL)

RESOLUTION_TTL_S = 60.0

_ACTIVE: dict = {"url": None, "role": None, "ts": 0.0}

OBSERVATIONS_SQL = """
SELECT id, source, source_record_id, observed_at, ingested_at,
       latitude, longitude,
       instrument, platform, confidence, frp, frp_unit,
       quality_flags, product_version, raw_properties, event_key
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
    settings = get_settings()
    return bool(settings.database_url or settings.database_url_fallback)


def db_status() -> str:
    if not USE_DB:
        return "not_configured"
    return "configured"


def reset_resolution() -> None:
    """Test hook: clear sticky DB tier decision."""
    _ACTIVE.update({"url": None, "role": None, "ts": 0.0})


def _connect_timeout(timeout: int | None = None) -> int:
    """Single connect timeout (Supabase pooler headroom)."""
    if timeout is not None:
        return timeout
    try:
        return int(get_settings().database_connect_timeout)
    except Exception:
        return 12


_POOLS: dict = {}
_POOLS_LOCK = threading.Lock()


def _pool_limits() -> tuple[int, int, float]:
    try:
        settings = get_settings()
        min_size = max(1, int(settings.database_pool_min_size))
        max_size = max(min_size, int(settings.database_pool_max_size))
        acquire = float(settings.database_pool_timeout)
    except Exception:
        min_size, max_size, acquire = 1, 5, 10.0
    return min_size, max_size, acquire


def get_pool(url: str, role: str = "query"):
    """One warm pool per tier URL (skips Supabase handshake)."""
    with _POOLS_LOCK:
        pool = _POOLS.get(url)
        if pool is not None and not pool.closed:
            return pool
    import psycopg.rows
    from psycopg_pool import ConnectionPool

    min_size, max_size, acquire = _pool_limits()
    pool = ConnectionPool(
        conninfo=url,
        open=True,
        min_size=min_size,
        max_size=max_size,
        timeout=acquire,
        kwargs={
            "connect_timeout": _connect_timeout(),
            "row_factory": psycopg.rows.dict_row,
            "prepare_threshold": None,
        },
        check=ConnectionPool.check_connection,
        name=f"pyra-{role}",
    )
    with _POOLS_LOCK:
        existing = _POOLS.get(url)
        if existing is not None and not existing.closed:
            pool.close()
            return existing
        _POOLS[url] = pool
        return pool


def close_pools() -> None:
    with _POOLS_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        try:
            pool.close()
        except Exception:
            pass


def pool_stats() -> dict:
    stats = {}
    with _POOLS_LOCK:
        items = list(_POOLS.items())
    for url, pool in items:
        try:
            info = pool.get_stats()
        except Exception:
            info = {}
        tail = url.split("@")[-1][:60] if "@" in url else url[:60]
        stats[tail] = info
    return stats


def _try_connect(url: str, timeout: int | None = None):
    pool = get_pool(url)
    if timeout is not None:
        return pool.connection(timeout=float(timeout))
    return pool.connection()


def resolve_database_url() -> tuple[str, str]:
    """Return (url, role): primary→fallback→local. Raises if none."""
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
            with _try_connect(url) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
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
    """Query one page plus one lookahead row"""
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


COUNT_SQL = """
SELECT COUNT(*) AS n
FROM observations
WHERE observed_at >= %(start)s
  AND observed_at <= %(end)s
  AND longitude >= %(min_lon)s AND longitude <= %(max_lon)s
  AND latitude >= %(min_lat)s AND latitude <= %(max_lat)s
  AND source = ANY (%(products)s)
"""


def fetch_count(start_iso: str, end_iso: str, bbox: list[float], products: list[str]) -> int:
    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "start": start_iso,
        "end": end_iso,
        "min_lon": min_lon,
        "max_lon": max_lon,
        "min_lat": min_lat,
        "max_lat": max_lat,
        "products": products,
    }
    url, _ = resolve_database_url()
    with _try_connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(COUNT_SQL, params)
            row = cur.fetchone()
    return row["n"] if row else 0


def fetch_freshness() -> dict:
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
