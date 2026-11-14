"""Synthetic fixture loader for M1 scaffold.

Clearly labelled synthetic data. No real FIRMS records here.
Covers a fixed Attica bbox + Aug 2024 window so frontend can integrate
before the real bounded ingest lands.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "synthetic_attica_aug2024.json"

# Fixed coverage the fixtures claim to represent. Requests outside this
# return coverage_status=unavailable, not empty.
FIXTURE_BBOX = (22.9, 37.7, 24.3, 38.5)  # min_lon, min_lat, max_lon, max_lat (Attica)
FIXTURE_START = datetime(2024, 8, 1, 0, 0, 0, tzinfo=UTC)
FIXTURE_END = datetime(2024, 8, 31, 23, 59, 59, tzinfo=UTC)

_cached: list[dict] | None = None


def load_fixtures() -> list[dict]:
    global _cached
    if _cached is not None:
        return _cached
    if not FIXTURE_PATH.exists():
        _cached = []
        return _cached
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        _cached = json.load(f)
    return _cached


def get_freshness() -> dict:
    records = load_fixtures()
    if not records:
        return {
            "latest_ingested_at": None,
            "synthetic": True,
            "note": "no fixture records loaded",
        }
    latest = max(r["ingested_at"] for r in records)
    return {
        "latest_ingested_at": latest,
        "synthetic": True,
        "note": "labelled synthetic fixtures for M1 integration; not FIRMS data",
    }
