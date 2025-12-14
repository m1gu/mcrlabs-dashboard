"""Schemas for GLIMS status events and dispensary ingest endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, validator


ALLOWED_STATUSES = {
    "Sample Received",
    "Generating",
    "Needs Second Check",
    "Second Check Done",
    "Reported",
    "Needs METRC Upload",
}


def _normalize_status(value: str) -> str:
    """Normalize status to title-case trimmed string."""
    norm = value.strip()
    return " ".join(part.capitalize() for part in norm.split())


class StatusEventCreate(BaseModel):
    sample_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    changed_at: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None
    source: str = Field(default="apps_script")

    @validator("sample_id")
    def _trim_sample_id(cls, value: str) -> str:
        return value.strip()

    @validator("status")
    def _validate_status(cls, value: str) -> str:
        normalized = _normalize_status(value)
        if normalized not in ALLOWED_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}")
        return normalized

    @validator("source")
    def _trim_source(cls, value: str) -> str:
        return value.strip()


class StatusEventResponse(BaseModel):
    id: int
    sample_id: str
    status: str
    changed_at: datetime
    created_at: datetime
    source: str
    metadata: Optional[dict[str, Any]] = None


class DispensarySuggestRequest(BaseModel):
    name: str = Field(..., min_length=1)
    sheet_line_number: int = Field(..., ge=1)

    @validator("name")
    def _trim_name(cls, value: str) -> str:
        return value.strip()


class DispensarySuggestResponse(BaseModel):
    id: int
    name: str
    sheet_line_number: int
    created_at: datetime
    processed: bool
    approved: bool
