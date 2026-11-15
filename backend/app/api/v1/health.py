from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import db

router = APIRouter()


@router.get("/health")
def health() -> JSONResponse:
    # No secrets, no internals.
    return JSONResponse(
        {
            "status": "ok",
            "checked_at": datetime.now(UTC).isoformat(),
            "database": "available" if db.db_configured() else "unavailable",
            "version": "0.1.0",
            "synthetic": True,
        }
    )
