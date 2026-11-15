"""FIRMS access: parsing, harmonization, upsert, and bounded on-demand fetch.

On-demand policy (request path may trigger a live fetch ONLY when all hold):
- MAP_KEY is configured server-side;
- the DB returned zero rows for the query (never alongside cached/DB data);
- the window is recent (end within ON_DEMAND_LOOKBACK_DAYS);
- the bbox area is within ON_DEMAND_MAX_DEG2;
- the global provider rate limit allows it (MIN_PROVIDER_INTERVAL_S).

The fetch window is clamped to the last 5 days (FIRMS API day-range cap).
History is the archive ingest's job, never the request path's.
"""

import csv
import hashlib
import io
import json
import logging
import time
import urllib.request
from datetime import UTC, datetime, timedelta

from app.settings import get_settings

log = logging.getLogger("pyra.firms")

FIRMS_API_HOST = "firms.modaps.eosdis.nasa.gov"

# SOURCE strings per the FIRMS web-services docs (/api/area/). No VERSION
# segment in the current API. NRT = near/real/ultra-real-time tail.
# Override without a code change via FIRMS_API_PRODUCTS, e.g.
#   {"modis": "MODIS_NRT", "viirs_n20": "VIIRS_NOAA20_NRT", ...}
# Unknown keys are rejected; missing keys keep the built-in defaults.
# Suomi NPP is excluded (spacecraft retired Nov 2026).
DEFAULT_API_PRODUCTS = {
    "modis": "MODIS_NRT",
    "viirs_n20": "VIIRS_NOAA20_NRT",
    "viirs_n21": "VIIRS_NOAA21_NRT",
}

MODIS_PLATFORMS = {"T": "Terra", "A": "Aqua"}
VIIRS_PLATFORMS = {"N": "Suomi NPP", "N20": "NOAA-20", "N21": "NOAA-21"}
LEGACY_SNPP_SOURCES = {"viirs_snpp"}

ON_DEMAND_LOOKBACK_DAYS = 10
ON_DEMAND_MAX_DEG2 = 50.0
ON_DEMAND_DAY_RANGE = 5
MIN_PROVIDER_INTERVAL_S = 60.0

_last_provider_call = 0.0

UPSERT_SQL = """
INSERT INTO observations
   (id, source, source_record_id, observed_at, ingested_at,
    latitude, longitude, geom,
    instrument, platform, confidence, frp, frp_unit,
    quality_flags, product_version, raw_properties, event_key)
 VALUES
   (%(id)s, %(source)s, %(source_record_id)s, %(observed_at)s, %(ingested_at)s,
    %(latitude)s, %(longitude)s,
    ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)::geography,
    %(instrument)s, %(platform)s, %(confidence)s, %(frp)s, %(frp_unit)s,
    %(quality_flags)s, %(product_version)s, %(raw_properties)s, %(event_key)s)
ON CONFLICT (source, source_record_id) DO UPDATE SET
  observed_at = EXCLUDED.observed_at,
  ingested_at = EXCLUDED.ingested_at,
  latitude = EXCLUDED.latitude,
  longitude = EXCLUDED.longitude,
  geom = EXCLUDED.geom,
  instrument = EXCLUDED.instrument,
  platform = EXCLUDED.platform,
  confidence = EXCLUDED.confidence,
  frp = EXCLUDED.frp,
  frp_unit = EXCLUDED.frp_unit,
  quality_flags = EXCLUDED.quality_flags,
   product_version = EXCLUDED.product_version,
   raw_properties = EXCLUDED.raw_properties,
   event_key = EXCLUDED.event_key
"""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def load_api_products() -> dict[str, str]:
    """API product strings, overridable via FIRMS_API_PRODUCTS JSON. Fail loudly."""
    raw = get_settings().firms_api_products.strip()
    if not raw:
        return dict(DEFAULT_API_PRODUCTS)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"FIRMS_API_PRODUCTS is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("FIRMS_API_PRODUCTS must be a JSON object of name->product string")
    unknown = sorted(set(parsed) - set(DEFAULT_API_PRODUCTS))
    if unknown:
        raise ValueError(f"FIRMS_API_PRODUCTS has unknown products: {unknown}")
    for key, value in parsed.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"FIRMS_API_PRODUCTS[{key!r}] must be a non-empty string")
    merged = dict(DEFAULT_API_PRODUCTS)
    merged.update(parsed)
    return merged


def map_key() -> str:
    return get_settings().firms_map_key


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [float(p.strip()) for p in value.split(",")]
    if len(parts) != 4:
        raise ValueError(f"bbox needs 4 numbers, got {value!r}")
    min_lon, min_lat, max_lon, max_lat = parts
    if not (min_lon < max_lon and min_lat < max_lat):
        raise ValueError(f"bbox ordering invalid: {value!r}")
    return min_lon, min_lat, max_lon, max_lat


def bbox_deg2(bbox: tuple[float, float, float, float] | list[float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bbox
    return (max_lon - min_lon) * (max_lat - min_lat)


def in_bbox(lat: float, lon: float, bbox: tuple | None) -> bool:
    if bbox is None:
        return True
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def detect_family(fieldnames: list[str]) -> str:
    names = {n.strip() for n in fieldnames}
    if "bright_ti4" in names:
        return "viirs"
    if "bright_t31" in names or "brightness" in names:
        return "modis"
    raise ValueError(
        f"unrecognized FIRMS columns: {sorted(names)}. The API product string "
        "may have changed; check the FIRMS web-services page and docs/harmonization.md."
    )


def parse_observed_at(acq_date: str, acq_time: str) -> datetime:
    dt = datetime.strptime(f"{acq_date.strip()} {acq_time.strip().zfill(4)}", "%Y-%m-%d %H%M")
    return dt.replace(tzinfo=UTC)


def _float_or_none(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def iter_raw_rows(lines, family: str | None = None):
    """Stream FIRMS CSV lines into raw row dicts. Skips invalid rows loudly."""
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        raise ValueError("empty CSV or missing header")
    family = family or detect_family(list(reader.fieldnames))
    if family not in ("modis", "viirs"):
        raise ValueError(f"family must be modis|viirs, got {family!r}")
    skipped = 0
    for line_no, row in enumerate(reader, start=2):
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("coords out of range")
            observed_at = parse_observed_at(row["acq_date"], row["acq_time"])
        except (KeyError, TypeError, ValueError) as exc:
            skipped += 1
            if skipped <= 5:
                log.warning("skip line %d: %s", line_no, exc)
            continue
        yield {
            "family": family,
            "raw": row,
            "latitude": lat,
            "longitude": lon,
            "observed_at": observed_at,
        }
    if skipped:
        log.info("skipped %d invalid rows", skipped)


def parse_firms_csv(text: str, family: str | None = None) -> list[dict]:
    """Parse FIRMS CSV text into raw row dicts. Skips invalid rows loudly."""
    rows = list(iter_raw_rows(io.StringIO(text), family=family))
    log.info("parsed %d rows", len(rows))
    return rows


def synth_source_record_id(
    source: str, satellite: str, observed_at: datetime, lat: float, lon: float, brightness: str
) -> str:
    basis = "|".join(
        [source, satellite, observed_at.isoformat(), f"{lat:.5f}", f"{lon:.5f}", brightness.strip()]
    )
    return hashlib.sha1(basis.encode()).hexdigest()


def event_key_for(lat: float, lon: float, observed_at: datetime) -> str:
    """Shared fire-event key: ~1 km cell + UTC day, across sensors.

    Twins from MODIS and VIIRS for the same fire get the same key while each
    row keeps its own id, provenance, and measurements. Mirrors the frontend
    corroboration cell rule. Naive datetimes are treated as UTC (the ingest
    path normalizes to UTC before harmonizing).
    """
    return f"{lat:.2f},{lon:.2f},{observed_at.date().isoformat()}"


def harmonize(parsed: dict, source: str, ingested_at: datetime) -> dict:
    """Map one parsed FIRMS row onto the harmonized observation record."""
    raw = parsed["raw"]
    family = parsed["family"]
    satellite = (raw.get("satellite") or "").strip()
    if family == "modis":
        platform = MODIS_PLATFORMS.get(satellite, satellite or None)
        instrument = "MODIS"
        brightness_col = "brightness"
        extra = {
            "bright_t31": raw.get("bright_t31") or None,
            "scan": raw.get("scan") or None,
            "track": raw.get("track") or None,
        }
    else:
        platform = VIIRS_PLATFORMS.get(satellite, satellite or None)
        instrument = "VIIRS"
        brightness_col = "bright_ti4"
        extra = {
            "bright_ti5": raw.get("bright_ti5") or None,
            "scan": raw.get("scan") or None,
            "track": raw.get("track") or None,
        }
    brightness = (raw.get(brightness_col) or "").strip()
    frp = _float_or_none(raw.get("frp"))
    confidence = (raw.get("confidence") or "").strip().lower() or None
    version = (raw.get("version") or "").strip() or None
    daynight = (raw.get("daynight") or "").strip().upper() or None
    raw_props = {"brightness": brightness or None, "daynight": daynight}
    raw_props.update({k: v for k, v in extra.items() if v not in (None, "")})

    source_record_id = synth_source_record_id(
        source,
        satellite,
        parsed["observed_at"],
        parsed["latitude"],
        parsed["longitude"],
        brightness,
    )
    return {
        "id": f"{source}-{source_record_id[:16]}",
        "source": source,
        "source_record_id": source_record_id,
        "event_key": event_key_for(parsed["latitude"], parsed["longitude"], parsed["observed_at"]),
        "observed_at": parsed["observed_at"],
        "ingested_at": ingested_at,
        "latitude": parsed["latitude"],
        "longitude": parsed["longitude"],
        "instrument": instrument,
        "platform": platform,
        "confidence": confidence,
        "frp": frp,
        "frp_unit": "MW" if frp is not None else None,
        "quality_flags": None,
        "product_version": version,
        "raw_properties": json.dumps(raw_props),
    }


def prepare_records(
    text: str, source: str, ingested_at: datetime, bbox: tuple | None, family: str | None = None
) -> list[dict]:
    if source in LEGACY_SNPP_SOURCES:
        raise ValueError("Suomi NPP ingest is disabled (spacecraft retired Nov 2026)")
    if source not in ("modis", "viirs"):
        raise ValueError(f"source must be modis|viirs, got {source!r}")
    parsed = parse_firms_csv(text, family=family or source)
    records = []
    for p in parsed:
        if not in_bbox(p["latitude"], p["longitude"], bbox):
            continue
        records.append(harmonize(p, source, ingested_at))
    # Dedupe identical content within one load (same synth ID).
    seen: dict[str, dict] = {}
    for r in records:
        seen[r["source_record_id"]] = r
    log.info("harmonized %d records (%d after dedupe)", len(records), len(seen))
    return list(seen.values())


def upsert_records(records: list[dict], database_url: str) -> int:
    from app import db as db_module

    if not records:
        return 0
    # Pooled write: same pooler-safe kwargs as reads (no prepared statements).
    with db_module.get_pool(database_url, role="ingest").connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, records)
    log.info("upserted %d records", len(records))
    return len(records)


def open_archive_text(path: str):
    """Open a .csv (or the first .csv inside a .zip) as a text stream. Caller closes."""
    import zipfile

    if path.lower().endswith(".zip"):
        zf = zipfile.ZipFile(path)
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            zf.close()
            raise ValueError(f"no CSV found in {path}")
        log.info("reading %s from %s", names[0], path)
        raw = zf.open(names[0])
        return io.TextIOWrapper(raw, encoding="utf-8", errors="replace"), zf
    return open(path, encoding="utf-8", errors="replace"), None


def stream_archive(
    path: str,
    source: str,
    ingested_at: datetime,
    bbox: tuple | None,
    database_url: str,
    batch_size: int = 2000,
) -> dict:
    """Stream an archive file (csv/zip) through harmonize+upsert in batches.

    Memory stays flat regardless of file size; only bbox-matching rows are kept.
    Returns a summary dict for verify-then-delete.
    """
    if source in LEGACY_SNPP_SOURCES:
        raise ValueError("Suomi NPP ingest is disabled (spacecraft retired Nov 2026)")
    if source not in ("modis", "viirs"):
        raise ValueError(f"source must be modis|viirs, got {source!r}")
    stream, closer = open_archive_text(path)
    seen: set[str] = set()
    total = kept = stored = 0
    batch: list[dict] = []
    try:
        for parsed in iter_raw_rows(stream, family=source):
            total += 1
            if not in_bbox(parsed["latitude"], parsed["longitude"], bbox):
                continue
            rec = harmonize(parsed, source, ingested_at)
            if rec["source_record_id"] in seen:
                continue
            seen.add(rec["source_record_id"])
            kept += 1
            batch.append(rec)
            if len(batch) >= batch_size:
                stored += upsert_records(batch, database_url)
                batch = []
                if total % 500000 == 0:
                    log.info("stream progress: %d scanned, %d kept, %d stored", total, kept, stored)
        if batch:
            stored += upsert_records(batch, database_url)
    finally:
        try:
            stream.close()
        finally:
            if closer is not None:
                closer.close()
    summary = {
        "file": path,
        "scanned": total,
        "kept": kept,
        "stored": stored,
        "ingested_at": ingested_at.isoformat(),
    }
    log.info("stream done: %s", summary)
    return summary


def fetch_api_csv(
    product: str, bbox: str, day_range: int, date: str, key: str, timeout_s: int = 30
) -> str:
    url = f"https://{FIRMS_API_HOST}/api/area/csv/{key}/{product}/{bbox}/{day_range}/{date}"
    req = urllib.request.Request(url, headers={"User-Agent": "Pyra/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (allowlisted below)
        if resp.status != 200:
            raise RuntimeError(f"FIRMS API returned HTTP {resp.status} for {product}")
        return resp.read().decode("utf-8", errors="replace")


def _source_for_product(name: str) -> str:
    return "modis" if name == "modis" else "viirs"


def on_demand_window(
    start: datetime, end: datetime, bbox: list[float] | tuple[float, ...]
) -> tuple[str, str, str] | None:
    """Clamped (start, end, bbox) fetch window, or None when out of policy."""
    now = _utcnow()
    if end < now - timedelta(days=ON_DEMAND_LOOKBACK_DAYS):
        return None  # historical gap: the archive ingest's job
    if bbox_deg2(bbox) > ON_DEMAND_MAX_DEG2:
        return None  # too wide for a live pull; serve what the DB has
    fetch_start = max(start, now - timedelta(days=ON_DEMAND_DAY_RANGE))
    fetch_end = min(end, now)
    if fetch_start > fetch_end:
        return None
    bbox_str = ",".join(str(v) for v in bbox)
    return fetch_start.date().isoformat(), fetch_end.date().isoformat(), bbox_str


def rate_limit_ok() -> bool:
    """One provider call per MIN_PROVIDER_INTERVAL_S, process-wide."""
    global _last_provider_call
    now = time.monotonic()
    if now - _last_provider_call < MIN_PROVIDER_INTERVAL_S:
        return False
    _last_provider_call = now
    return True


def reset_rate_limit() -> None:
    """Tests only."""
    global _last_provider_call
    _last_provider_call = 0.0


def fetch_live_records(
    products: dict[str, str],
    sources: list[str],
    bbox: list[float],
    fetch_end: str,
    timeout_s: int = 8,
) -> tuple[list[dict], list[dict]]:
    """Bounded live pull with NO persistence. Returns (records, failures).

    Same provider call as the ingest path, but rows are returned, never
    written. Used by live mode and the on-demand read path (which upserts).
    """
    key = map_key()
    if not key:
        raise ValueError("FIRMS_MAP_KEY is not set")
    ingested_at = _utcnow()
    bbox_tuple = tuple(bbox)
    bbox_str = ",".join(str(v) for v in bbox)
    out: list[dict] = []
    failures: list[dict] = []
    for name, product in products.items():
        source = _source_for_product(name)
        if source not in sources:
            continue
        try:
            text = fetch_api_csv(product, bbox_str, ON_DEMAND_DAY_RANGE, fetch_end, key, timeout_s)
        except Exception as exc:
            log.error("live fetch failed for %s (%s): %s", name, product, exc)
            failures.append({"name": name, "product": product, "stage": "fetch", "error": str(exc)})
            continue
        try:
            out.extend(prepare_records(text, source, ingested_at, bbox_tuple))
        except Exception as exc:
            log.error("live payload rejected for %s (%s): %s", name, product, exc)
            failures.append({"name": name, "product": product, "stage": "parse", "error": str(exc)})
            continue
    return out, failures


def fetch_and_store(
    products: dict[str, str],
    sources: list[str],
    bbox: list[float],
    fetch_end: str,
    database_url: str,
) -> tuple[int, list[dict]]:
    """Bounded live pull for the requested sources. Returns (rows, failures)."""
    records, failures = fetch_live_records(products, sources, bbox, fetch_end, timeout_s=30)
    total = upsert_records(records, database_url)
    return total, failures
