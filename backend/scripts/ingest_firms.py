"""FIRMS ingest CLI. Thin wrapper over app.firms (importable, testable).

Usage (from backend/):
  uv run python scripts/ingest_firms.py archive --csv FILE.csv --source modis
  uv run python scripts/ingest_firms.py archive --csv F.csv --source viirs \
    --bbox=-3.3,4.5,1.2,11.2
  uv run python scripts/ingest_firms.py api --bbox=-3.3,4.5,1.2,11.2 --day-range 5
  uv run python scripts/ingest_firms.py api --bbox=-3.3,4.5,1.2,11.2 --date D --check

Env: DATABASE_URL (required, except api --check), FIRMS_MAP_KEY (api subcommand
only), FIRMS_API_PRODUCTS (optional JSON override of product strings).
"""

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime

from app.firms import (
    DEFAULT_API_PRODUCTS,
    detect_family,
    fetch_api_csv,
    harmonize,
    iter_raw_rows,
    load_api_products,
    open_archive_text,
    parse_bbox,
    parse_firms_csv,
    prepare_records,
    stream_archive,
    synth_source_record_id,
    upsert_records,
)

__all__ = [
    "DEFAULT_API_PRODUCTS",
    "detect_family",
    "fetch_api_csv",
    "harmonize",
    "iter_raw_rows",
    "load_api_products",
    "open_archive_text",
    "parse_bbox",
    "parse_firms_csv",
    "prepare_records",
    "stream_archive",
    "synth_source_record_id",
    "upsert_records",
    "main",
]

log = logging.getLogger("pyra.ingest")


def cmd_archive(args: argparse.Namespace) -> int:
    from app.firms import stream_archive

    bbox = parse_bbox(args.bbox) if args.bbox else None
    database_url = args.database_url or os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL is not set (or pass --database-url)", file=sys.stderr)
        return 2
    ingested_at = datetime.now(UTC)
    # Streams csv/zip in batches; memory stays flat on multi-GB files.
    summary = stream_archive(args.csv, args.source, ingested_at, bbox, database_url)
    print(json.dumps(summary))
    return 0


def cmd_check(args: argparse.Namespace, products: dict[str, str], map_key: str) -> int:
    """Probe each product with a 1-day pull. No DB writes. Exit non-zero on drift."""
    report: dict[str, list] = {"checked": [], "failed": []}
    for name, product in products.items():
        try:
            text = fetch_api_csv(product, args.bbox, 1, args.date, map_key)
            rows = parse_firms_csv(text)
            report["checked"].append({"name": name, "product": product, "rows": len(rows)})
            log.info("check ok: %s (%s) returned %d rows", name, product, len(rows))
        except Exception as exc:
            log.error("check FAILED for %s (%s): %s", name, product, exc)
            report["failed"].append({"name": name, "product": product, "error": str(exc)})
    print(json.dumps(report))
    return 1 if report["failed"] else 0


def cmd_api(args: argparse.Namespace) -> int:
    map_key = os.environ.get("FIRMS_MAP_KEY", "")
    if not map_key:
        print("FIRMS_MAP_KEY is not set", file=sys.stderr)
        return 2
    if not args.bbox:
        print("--bbox is required for api ingest (bounded area only)", file=sys.stderr)
        return 2
    parse_bbox(args.bbox)  # validate early
    if not 1 <= args.day_range <= 5:
        # FIRMS API cap: day range must be within [1..5].
        print(f"--day-range must be within [1..5], got {args.day_range}", file=sys.stderr)
        return 2
    try:
        products = load_api_products()
    except ValueError as exc:
        print(f"bad FIRMS_API_PRODUCTS: {exc}", file=sys.stderr)
        return 2
    if args.check:
        return cmd_check(args, products, map_key)
    ingested_at = datetime.now(UTC)
    total = 0
    failures = []
    database_url = args.database_url or os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL is not set (or pass --database-url)", file=sys.stderr)
        return 2
    for name, product in products.items():
        source = "modis" if name == "modis" else "viirs"
        try:
            text = fetch_api_csv(product, args.bbox, args.day_range, args.date, map_key)
        except Exception as exc:
            log.error("API fetch failed for %s (%s): %s", name, product, exc)
            failures.append({"name": name, "product": product, "stage": "fetch", "error": str(exc)})
            continue
        try:
            records = prepare_records(text, source, ingested_at, parse_bbox(args.bbox))
        except Exception as exc:
            log.error("API payload rejected for %s (%s): %s", name, product, exc)
            failures.append({"name": name, "product": product, "stage": "parse", "error": str(exc)})
            continue
        total += upsert_records(records, database_url)
    print(
        json.dumps(
            {"rows_upserted": total, "failed": failures, "ingested_at": ingested_at.isoformat()}
        )
    )
    if failures:
        log.error("api ingest partially failed: %d of %d products", len(failures), len(products))
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest FIRMS hotspot CSVs into Postgres")
    parser.add_argument(
        "--database-url",
        default=None,
        help="override DATABASE_URL (e.g. load the fallback store instead of primary)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_arc = sub.add_parser("archive", help="ingest a downloaded FIRMS archive CSV")
    p_arc.add_argument("--csv", required=True, help="path to FIRMS CSV file")
    p_arc.add_argument("--source", required=True, choices=["modis", "viirs"])
    p_arc.add_argument("--bbox", default=None, help="min_lon,min_lat,max_lon,max_lat filter")
    p_arc.set_defaults(func=cmd_archive)

    p_api = sub.add_parser("api", help="pull the NRT tail from the FIRMS API")
    p_api.add_argument("--bbox", required=True, help="bounded area, e.g. -3.3,4.5,1.2,11.2")
    p_api.add_argument("--day-range", type=int, default=5, help="1..5 (FIRMS API cap)")
    p_api.add_argument("--date", required=True, help="end date YYYY-MM-DD")
    p_api.add_argument(
        "--check",
        action="store_true",
        help="probe products with a 1-day pull; no DB writes; exit 1 on drift",
    )
    p_api.set_defaults(func=cmd_api)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    if getattr(args, "check", False):
        return args.func(args)  # --check probes the provider; no DATABASE_URL needed
    if not getattr(args, "database_url", None) and "DATABASE_URL" not in os.environ:
        print("DATABASE_URL is not set (or pass --database-url)", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
