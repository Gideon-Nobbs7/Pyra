from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import db
from app.fixtures import get_freshness

router = APIRouter()


def _freshness() -> tuple[dict, bool]:
    """DB freshness when a store answers, else the fixture statement. Never raises."""
    if db.db_configured():
        try:
            fresh = db.fetch_freshness()
            return fresh, bool(fresh.get("synthetic", False))
        except Exception:
            pass
    return get_freshness(), True


PRODUCTS = [
    {
        "source": "modis",
        "product": "MODIS Collection 6.1 active fire (MCD14DL)",
        "version": "6.1",
        "coverage_start": "2000-11-01T00:00:00+00:00",
        "coverage_end": None,
        "limitations": [
            "1 km pixels; center point is not the fire location.",
            "Suomi NPP VIIRS is excluded: the spacecraft stopped delivering data on 2 Nov 2026.",
        ],
    },
    {
        "source": "viirs",
        "product": "VIIRS 375 m active fire, NOAA-20 (VJ114IMGTDL_NRT)",
        "version": "1.0NRT",
        "coverage_start": "2018-04-01T00:00:00+00:00",
        "coverage_end": None,
        "limitations": [
            "375 m pixels; greater small-fire response than MODIS.",
        ],
    },
    {
        "source": "viirs",
        "product": "VIIRS 375 m active fire, NOAA-21 (VJ214IMGTDL_NRT)",
        "version": "1.0NRT",
        "coverage_start": "2023-03-01T00:00:00+00:00",
        "coverage_end": None,
        "limitations": [
            "375 m pixels; greater small-fire response than MODIS.",
        ],
    },
]

GLOBAL_LIMITATIONS = [
    "A satellite hotspot is a detection, not a confirmed wildfire, perimeter, or burned area.",
    "Zero detections do not prove no fire occurred.",
    "Observation time and ingestion time are distinct fields.",
    "We acknowledge the use of NASA FIRMS data and imagery, part of NASA LANCE/ESDIS. "
    "FIRMS information is provided 'as is'.",
]


@router.get("/metadata")
def metadata() -> JSONResponse:
    freshness, synthetic = _freshness()
    return JSONResponse(
        {
            "products": PRODUCTS,
            "harmonization": {
                "method": "Two-sensor harmonized hotspot series; resolutions, sensitivities, "
                "and overpass schedules reconciled per docs/harmonization.md. "
                "A harmonized count is a detection count, never fires or burned area.",
                "documentation_url": None,
            },
            "freshness": {
                "latest_ingested_at": freshness.get("latest_ingested_at"),
                "store": freshness.get("store"),
                "synthetic": freshness.get("synthetic", synthetic),
            },
            "limitations": GLOBAL_LIMITATIONS,
            "synthetic": synthetic,
        }
    )
