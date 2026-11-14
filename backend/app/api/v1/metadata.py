from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.fixtures import FIXTURE_BBOX, FIXTURE_END, FIXTURE_START, get_freshness

router = APIRouter()


@router.get("/metadata")
def metadata() -> JSONResponse:
    return JSONResponse(
        {
            "products": [
                {
                    "source": "modis",
                    "name": "MODIS Collection 6.1 active fire (MCD14DL)",
                    "coverage": "1 Nov 2000 to present (FIRMS Archive Download)",
                    "confidence": "source-defined l/n/h; see docs/harmonization.md",
                    "frp_unit": "MW",
                },
                {
                    "source": "viirs",
                    "name": "VIIRS 375m active fire, NOAA-20 (VJ114IMGTDL_NRT)",
                    "coverage": "1 Apr 2018 to present (FIRMS Archive Download)",
                    "confidence": "source-defined l/n/h; see docs/harmonization.md",
                    "frp_unit": "MW",
                },
                {
                    "source": "viirs",
                    "name": "VIIRS 375m active fire, NOAA-21 (VJ214IMGTDL_NRT)",
                    "coverage": "1 Mar 2023 to present (FIRMS Archive Download)",
                    "confidence": "source-defined l/n/h; see docs/harmonization.md",
                    "frp_unit": "MW",
                },
            ],
            "coverage": {
                "fixture_bbox": list(FIXTURE_BBOX),
                "fixture_start": FIXTURE_START.isoformat(),
                "fixture_end": FIXTURE_END.isoformat(),
            },
            "freshness": get_freshness(),
            "fields": [
                "id",
                "source",
                "source_record_id",
                "observed_at",
                "ingested_at",
                "latitude",
                "longitude",
                "instrument",
                "platform",
                "confidence",
                "frp",
                "frp_unit",
                "quality_flags",
                "product_version",
                "raw_properties",
            ],
            "limitations": [
                "A satellite hotspot is a detection, not a confirmed "
                "wildfire, perimeter, or burned area.",
                "Zero detections do not prove no fire occurred.",
                "Serving labelled synthetic fixtures until the FIRMS ingest runs.",
                "Observation time and ingestion time are distinct fields.",
                "Suomi NPP VIIRS is excluded: the spacecraft stopped delivering "
                "data on 2 Nov 2026.",
                "We acknowledge the use of NASA FIRMS data and imagery, part of "
                "NASA LANCE/ESDIS. FIRMS information is provided 'as is'.",
            ],
            "synthetic": True,
        }
    )
