"""Minimal GEE FIRMS raster ingest: bbox x date range -> PostGIS.

MODIS-first slice of the EE adapter (spike-validated): enumerates every fire
pixel deterministically via tiled sampleRectangle, maps to the harmonized
record shape, and upserts idempotently. Bounded: refuses ranges over 31 days.
No EE writes; reads only. Table stakes: EE_PROJECT + EE_CREDENTIALS_PATH env.
"""

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta

log = logging.getLogger("pyra.ee_ingest")

MAX_DAYS = 31
MAX_CELLS_PER_TILE = 200000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest GEE FIRMS raster pixels into Postgres")
    parser.add_argument("--collection", default="FIRMS")
    parser.add_argument("--bbox", required=True, help="min_lon,min_lat,max_lon,max_lat")
    parser.add_argument("--start", required=True, help="first date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="day after last date YYYY-MM-DD")
    parser.add_argument("--source", default="modis", choices=["modis"])
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--tile-deg", type=float, default=1.5)
    return parser


def _ee():
    import ee

    project = os.environ.get("EE_PROJECT", "")
    key_path = os.path.expanduser(os.environ.get("EE_CREDENTIALS_PATH", ""))
    if not project or not key_path:
        print("EE_PROJECT and EE_CREDENTIALS_PATH must be set", file=sys.stderr)
        raise SystemExit(2)
    ee.Initialize(ee.ServiceAccountCredentials(None, key_path), project=project)
    return ee


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    database_url = args.database_url or os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL is not set (or pass --database-url)", file=sys.stderr)
        return 2
    from app import firms as firms_lib

    min_lon, min_lat, max_lon, max_lat = (float(p) for p in args.bbox.split(","))
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)
    ndays = (end - start).days
    if not 1 <= ndays <= MAX_DAYS:
        print(f"date range must be 1..{MAX_DAYS} days, got {ndays}", file=sys.stderr)
        return 2

    ee = _ee()
    col = (
        ee.ImageCollection(args.collection)
        .filterDate(args.start, args.end)
        .sort("system:time_start")
    )
    ids = col.aggregate_array("system:index").getInfo()
    log.info("EE window %s..%s: %d daily images", args.start, args.end, len(ids))

    ingested_at = datetime.now(UTC)
    total = 0
    per_day = []
    day = start
    one_day = timedelta(days=1)
    while day < end:
        day_str = day.strftime("%Y-%m-%d")
        next_str = (day + one_day).strftime("%Y-%m-%d")
        img = (
            ee.ImageCollection(args.collection)
            .filterDate(day_str, next_str)
            .filterBounds(ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat]))
            .first()
        )
        info = img.getInfo() if img else None
        if info is None:
            per_day.append({"date": day_str, "stored": 0, "note": "no image"})
            day += one_day
            continue
        tiled = img.select(["T21", "confidence", "line_number"])
        batch: list[dict] = []
        lon = min_lon
        while lon < max_lon:
            lat = min_lat
            while lat < max_lat:
                x1, y1 = lon, lat
                x2, y2 = min(lon + args.tile_deg, max_lon), min(lat + args.tile_deg, max_lat)
                grid = tiled.sampleRectangle(
                    region=ee.Geometry.Rectangle([x1, y1, x2, y2]), defaultValue=0
                ).getInfo()
                props = grid.get("properties", {})
                t21s = props.get("T21", [])
                confs = props.get("confidence", [])
                lns = props.get("line_number", [])
                nrows = len(t21s)
                ncols = len(t21s[0]) if nrows else 0
                for r in range(nrows):
                    for c_ in range(min(len(t21s[r]), ncols)):
                        t21 = t21s[r][c_]
                        if not t21:
                            continue
                        clon = round(x1 + (c_ + 0.5) * (x2 - x1) / max(ncols, 1), 5)
                        clat = round(y2 - (r + 0.5) * (y2 - y1) / max(nrows, 1), 5)
                        conf = confs[r][c_] if r < len(confs) and c_ < len(confs[r]) else None
                        ln = lns[r][c_] if r < len(lns) and c_ < len(lns[r]) else None
                        sid = firms_lib.synth_source_record_id(
                            args.source, "", day, clon, clat, str(t21)
                        )
                        batch.append(
                            {
                                "id": f"{args.source}-{sid[:16]}",
                                "source": args.source,
                                "source_record_id": sid,
                                "observed_at": day,
                                "ingested_at": ingested_at,
                                "latitude": clat,
                                "longitude": clon,
                                "instrument": "MODIS",
                                "platform": None,
                                "confidence": str(conf) if conf is not None else None,
                                "frp": None,
                                "frp_unit": None,
                                "quality_flags": None,
                                "product_version": "6.0-rasterized (GEE)",
                                "raw_properties": json.dumps(
                                    {
                                        "brightness": t21,
                                        "line_number": ln,
                                        "source_collection": args.collection,
                                    }
                                ),
                            }
                        )
                lat += args.tile_deg
            lon += args.tile_deg
        stored = firms_lib.upsert_records(batch, database_url)
        total += stored
        per_day.append({"date": day_str, "pixels": len(batch), "stored": stored})
        log.info("EE %s: %d pixels stored", day_str, stored)
        day += one_day
    print(
        json.dumps({"days": per_day, "total_stored": total, "ingested_at": ingested_at.isoformat()})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
