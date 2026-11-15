"""One ingest window: route recent+small to FIRMS, history/wide to EE.

Unit of work for the background worker and for manual one-shots. Thin glue
over app.firms and scripts.ee_ingest; importable and testable.

Usage (from backend/):
  uv run python scripts/ingest_window.py --bbox=-3.3,4.5,1.2,11.2
  uv run python scripts/ingest_window.py --bbox=-3.3,4.5,1.2,11.2 \
    --start 2024-08-10 --end 2024-08-17
  uv run python scripts/ingest_window.py --bbox=-3.3,4.5,1.2,11.2 --source-policy ee

Defaults cover the rolling recent window (end=today, start=end-6d).
Exit codes: 0 ok, 1 provider/store failure or partial, 2 config/usage.
"""

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta

from app import db as db_module
from app import firms as firms_lib
from app.settings import get_settings

log = logging.getLogger("pyra.ingest_window")

EE_MAX_DAYS = 31  # mirrors scripts.ee_ingest.MAX_DAYS (EE quota bound)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def choose_source(
    start: datetime, end: datetime, bbox: list[float], *, map_key: str, ee_ready: bool
) -> tuple[str, str]:
    """Pick 'firms', 'ee', or 'none' for the window, with a reason.

    FIRMS owns the recent small tail; EE owns everything older or wider.
    Pure decision function: no network, no DB.
    """
    if firms_lib.on_demand_window(start, end, bbox) is not None and map_key:
        return "firms", "recent small window with MAP key"
    if ee_ready:
        return "ee", "history or wide window via EE raster"
    if firms_lib.on_demand_window(start, end, bbox) is None:
        return "none", (
            "window is outside the live FIRMS bounds (recent 10d, 50 deg2) "
            "and EE credentials are not configured"
        )
    return "none", "FIRMS_MAP_KEY is not set and EE credentials are not configured"


def _resolve_tier(database_url: str | None) -> tuple[str, str]:
    if database_url:
        return database_url, "override"
    try:
        return db_module.resolve_database_url()
    except ConnectionError as exc:
        raise RuntimeError(f"no database store reachable: {exc}") from exc


def run_firms_window(
    bbox: list[float],
    start: datetime,
    end: datetime,
    database_url: str,
    map_key: str,
    timeout_s: int = 30,
) -> dict:
    """Pull the FIRMS tail for the window and upsert. Returns a summary dict."""
    bbox_str = ",".join(str(v) for v in bbox)
    days = max(1, (end.date() - start.date()).days + 1)
    day_range = min(days, firms_lib.ON_DEMAND_DAY_RANGE)
    tail_only = days > firms_lib.ON_DEMAND_DAY_RANGE
    products = firms_lib.load_api_products()
    ingested_at = _utcnow()
    total = 0
    failures = []
    for name, product in products.items():
        source = "modis" if name == "modis" else "viirs"
        try:
            text = firms_lib.fetch_api_csv(
                product, bbox_str, day_range, end.date().isoformat(), map_key, timeout_s
            )
        except Exception as exc:
            log.error("API fetch failed for %s (%s): %s", name, product, exc)
            failures.append({"name": name, "product": product, "stage": "fetch", "error": str(exc)})
            continue
        try:
            records = firms_lib.prepare_records(text, source, ingested_at, tuple(bbox))
        except Exception as exc:
            log.error("API payload rejected for %s (%s): %s", name, product, exc)
            failures.append({"name": name, "product": product, "stage": "parse", "error": str(exc)})
            continue
        total += firms_lib.upsert_records(records, database_url)
    return {
        "source": "firms",
        "window_days": days,
        "day_range": day_range,
        "tail_only": tail_only,
        "rows_upserted": total,
        "failures": failures,
        "ingested_at": ingested_at.isoformat(),
    }


def run_ee_window(bbox: list[float], start: datetime, end: datetime, database_url: str) -> dict:
    """Delegate wide/history windows to ee_ingest in MAX_DAYS chunks."""
    from scripts import ee_ingest

    bbox_str = ",".join(str(v) for v in bbox)
    chunks = []
    cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = end.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor <= end_day:
        chunk_end = min(cursor + timedelta(days=EE_MAX_DAYS - 1), end_day)
        # ee_ingest --end is exclusive (day after the last date).
        exclusive_end = (chunk_end + timedelta(days=1)).date().isoformat()
        chunks.append((cursor.date().isoformat(), exclusive_end))
        cursor = chunk_end + timedelta(days=1)
    results = []
    for chunk_start, chunk_end in chunks:
        code = ee_ingest.main(
            [
                f"--bbox={bbox_str}",
                f"--start={chunk_start}",
                f"--end={chunk_end}",
                f"--database-url={database_url}",
            ]
        )
        results.append({"start": chunk_start, "end": chunk_end, "exit": code})
    failed = [r for r in results if r["exit"] != 0]
    return {
        "source": "ee",
        "chunks": results,
        "failures": [
            {"stage": "ee_chunk", "error": f"exit {r['exit']} for {r['start']}..{r['end']}"}
            for r in failed
        ],
    }


def _parse_day(value: str, name: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError(f"--{name} must be YYYY-MM-DD, got {value!r}") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest one window (FIRMS tail or EE raster)")
    parser.add_argument("--bbox", required=True, help="min_lon,min_lat,max_lon,max_lat")
    parser.add_argument("--start", default=None, help="first date YYYY-MM-DD (default: end-6d)")
    parser.add_argument("--end", default=None, help="last date YYYY-MM-DD (default: today UTC)")
    parser.add_argument(
        "--source-policy",
        default="auto",
        choices=["auto", "firms", "ee"],
        help="auto routes by window; firms/ee force a path",
    )
    parser.add_argument("--database-url", default=None, help="override tier resolution")
    parser.add_argument("--timeout", type=int, default=30, help="FIRMS fetch timeout seconds")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in args.bbox.split(","))
    except ValueError:
        print(f"--bbox must be 4 numbers, got {args.bbox!r}", file=sys.stderr)
        return 2
    if not (min_lon < max_lon and min_lat < max_lat):
        print(f"--bbox ordering invalid: {args.bbox!r}", file=sys.stderr)
        return 2
    bbox = [min_lon, min_lat, max_lon, max_lat]
    try:
        end = _parse_day(args.end, "end") if args.end else _utcnow()
        start = (
            _parse_day(args.start, "start")
            if args.start
            else (end - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if end < start:
        print("--end must be >= --start", file=sys.stderr)
        return 2

    settings = get_settings()
    # EE credentials live in root .env; ee_ingest reads process env, so bridge
    # them only when the shell did not already provide them.
    if settings.ee_project:
        os.environ.setdefault("EE_PROJECT", settings.ee_project)
    if settings.ee_credentials_path:
        path = os.path.expanduser(settings.ee_credentials_path)
        os.environ.setdefault("EE_CREDENTIALS_PATH", path)
    map_key = settings.firms_map_key
    ee_ready = bool(os.environ.get("EE_PROJECT") and os.environ.get("EE_CREDENTIALS_PATH"))

    if args.source_policy == "auto":
        source, reason = choose_source(start, end, bbox, map_key=map_key, ee_ready=ee_ready)
    elif args.source_policy == "firms":
        if not map_key:
            print("FIRMS_MAP_KEY is not set", file=sys.stderr)
            return 2
        source, reason = "firms", "forced via --source-policy"
    else:
        if not ee_ready:
            print("EE_PROJECT and EE_CREDENTIALS_PATH must be set", file=sys.stderr)
            return 2
        source, reason = "ee", "forced via --source-policy"
    log.info("window %s..%s source=%s (%s)", start.date(), end.date(), source, reason)

    if source == "none":
        print(reason, file=sys.stderr)
        return 2
    try:
        url, tier = _resolve_tier(args.database_url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if source == "firms":
        try:
            summary = run_firms_window(bbox, start, end, url, map_key, args.timeout)
        except ValueError as exc:
            print(f"bad FIRMS_API_PRODUCTS: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            print(f"firms ingest failed: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            summary = run_ee_window(bbox, start, end, url)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            print(f"ee ingest exited {code}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"ee ingest failed: {exc}", file=sys.stderr)
            return 1
    summary.update(
        {
            "tier": tier,
            "bbox": bbox,
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "route_reason": reason,
        }
    )
    print(json.dumps(summary))
    return 1 if summary.get("failures") else 0


if __name__ == "__main__":
    raise SystemExit(main())
