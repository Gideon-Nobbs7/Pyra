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
            "version": "0.1.0",
            "database": db.db_status(),
            "synthetic": True,
        }
    )
