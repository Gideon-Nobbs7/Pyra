"""Observation schemas: minimum fields, nulls stay null, UTC timestamps."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Observation(BaseModel):
    id: str
    source: Literal["modis", "viirs"]
    source_record_id: str | None = None
    observed_at: datetime
    ingested_at: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    instrument: str | None = None
    platform: str | None = None
    confidence: str | None = None
    frp: float | None = None
    frp_unit: str | None = None
    quality_flags: str | None = None
    product_version: str | None = None
    raw_properties: dict[str, Any] | None = None


class Pagination(BaseModel):
    limit: int
    cursor_next: str | None = None
    has_more: bool = False


class ObservationsResponse(BaseModel):
    data: list[Observation]
    pagination: Pagination
    filters_applied: dict[str, Any]
    freshness: dict[str, Any]
    coverage_status: Literal["ok", "empty", "unavailable"]
    coverage_reason: str
    synthetic: bool = True


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
