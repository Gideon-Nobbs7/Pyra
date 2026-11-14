"""Earth Engine spike: inspect the FIRMS raster collection. Read-only, no DB writes.

Proves (or kills) the GEE-history plan with real pixels before any adapter
work: band names, per-pixel properties, date granularity, and a count
cross-check window against FIRMS CSV for the same bbox+week.

Usage:
  EE_PROJECT=<id> EE_CREDENTIALS_PATH=~/.secrets/pyra-ee-key.json \\
    uv run python scripts/ee_spike.py --bbox=-3.3,4.5,1.2,11.2 --start 2024-08-10 --end 2024-08-17
"""

import argparse
import json
import logging
import os
import sys

log = logging.getLogger("pyra.ee_spike")

GHANA_BBOX = (-3.3, 4.5, 1.2, 11.2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect EE FIRMS raster (read-only)")
    parser.add_argument(
        "--bbox", default=",".join(map(str, GHANA_BBOX)), help="min_lon,min_lat,max_lon,max_lat"
    )
    parser.add_argument("--start", default="2024-08-10", help="first date YYYY-MM-DD")
    parser.add_argument("--end", default="2024-08-17", help="day after last date YYYY-MM-DD")
    parser.add_argument("--collection", default="FIRMS", help="EE image collection id")
    parser.add_argument("--max-pixels", type=int, default=5, help="sample pixels to print")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    project = os.environ.get("EE_PROJECT", "").strip()
    key_path = os.path.expanduser(os.environ.get("EE_CREDENTIALS_PATH", "").strip())
    if not project or not key_path:
        print("EE_PROJECT and EE_CREDENTIALS_PATH must be set", file=sys.stderr)
        return 2
    if not os.path.exists(key_path):
        print(f"credentials file not found: {key_path}", file=sys.stderr)
        return 2

    import ee  # noqa: E402 (only needed for live runs, not for --help/errors)

    credentials = ee.ServiceAccountCredentials(None, key_path)
    ee.Initialize(credentials, project=project)

    min_lon, min_lat, max_lon, max_lat = (float(p) for p in args.bbox.split(","))
    col = ee.ImageCollection(args.collection).filterDate(args.start, args.end)
    size = col.size().getInfo()
    print(
        json.dumps(
            {
                "collection": args.collection,
                "window": [args.start, args.end],
                "bbox": args.bbox,
                "images": size,
            }
        )
    )

    info = col.limit(3).getInfo()
    for feat in info.get("features", []):
        props = feat.get("properties", {})
        print(
            json.dumps(
                {
                    "id": feat.get("id"),
                    "bands": [b["id"] for b in feat.get("bands", [])],
                    "date_keys": sorted(
                        k
                        for k in props
                        if "time" in k.lower() or "date" in k.lower() or "start" in k.lower()
                    ),
                    "system_time_start": props.get("system:time_start"),
                    "sample_props": {k: props[k] for k in sorted(props)[:15]},
                }
            )
        )
    if size == 0:
        print(json.dumps({"samples": [], "note": "no images in window"}))
        return 0

    first = ee.Image(col.first())
    # sample() silently returns nothing on these rasters; tiled sampleRectangle
    # with arithmetic centroids enumerates every fire pixel deterministically.
    # sampleRectangle caps at 262144 px, so tile the bbox (~1km cells).
    # Orientation assumption: row 0 = northernmost row (to be validated against
    # FIRMS CSV overlap: GEE Ghana 2001 vs archived CSV rows in Supabase).
    span = max_lon - min_lon
    tile = max(span / max(1, int(span / 1.5) + 1), 0.05)
    tiled = first.select(["T21", "confidence", "line_number"])
    feats = []
    lon = min_lon
    while lon < max_lon and len(feats) < args.max_pixels:
        lat = min_lat
        while lat < max_lat and len(feats) < args.max_pixels:
            x1, y1 = lon, lat
            x2, y2 = min(lon + tile, max_lon), min(lat + tile, max_lat)
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
                row_t = t21s[r]
                row_c = confs[r] if r < len(confs) else []
                row_l = lns[r] if r < len(lns) else []
                for c_ in range(min(len(row_t), ncols)):
                    if row_t[c_]:
                        feats.append(
                            {
                                "lon": round(x1 + (c_ + 0.5) * (x2 - x1) / max(ncols, 1), 5),
                                "lat": round(y2 - (r + 0.5) * (y2 - y1) / max(nrows, 1), 5),
                                "T21": row_t[c_],
                                "confidence": row_c[c_] if c_ < len(row_c) else None,
                                "line_number": row_l[c_] if c_ < len(row_l) else None,
                            }
                        )
                        if len(feats) >= args.max_pixels:
                            break
                if len(feats) >= args.max_pixels:
                    break
            lat += tile
        lon += tile
    print(json.dumps({"samples": feats, "count": len(feats)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
