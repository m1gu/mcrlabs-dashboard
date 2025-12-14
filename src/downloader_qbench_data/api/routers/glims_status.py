"""API v2 endpoints for GLIMS status events and dispensary ingest."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from downloader_qbench_data.api.dependencies import get_db_session, require_active_user
from downloader_qbench_data.api.schemas.glims_status import (
    ALLOWED_STATUSES,
    DispensarySuggestRequest,
    DispensarySuggestResponse,
    StatusEventCreate,
    StatusEventResponse,
)

router = APIRouter(
    prefix="/api/v2/glims",
    tags=["glims-status"],
    dependencies=[Depends(require_active_user)],
)


def _normalize_status(value: str) -> str:
    return " ".join(part.capitalize() for part in value.strip().split())


@router.post(
    "/status-events",
    response_model=StatusEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_status_event(
    payload: StatusEventCreate,
    session: Session = Depends(get_db_session),
) -> StatusEventResponse:
    sample_id = payload.sample_id.strip()
    status_norm = _normalize_status(payload.status)
    if status_norm not in ALLOWED_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_STATUSES))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Allowed: {allowed}")

    exists = session.execute(
        text("SELECT 1 FROM glims_samples WHERE sample_id = :sid LIMIT 1"),
        {"sid": sample_id},
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sample_not_found")

    params = {
        "sample_id": sample_id,
        "status": status_norm,
        "changed_at": payload.changed_at or datetime.utcnow(),
        "source": payload.source.strip() or "apps_script",
        "metadata": payload.metadata,
    }

    row = session.execute(
        text(
            """
            INSERT INTO glims_samples_status_events (sample_id, status, changed_at, source, metadata)
            VALUES (:sample_id, :status, :changed_at, :source, :metadata)
            RETURNING id, sample_id, status, changed_at, created_at, source, metadata
            """
        ),
        params,
    ).one()

    return StatusEventResponse(
        id=row.id,
        sample_id=row.sample_id,
        status=row.status,
        changed_at=row.changed_at,
        created_at=row.created_at,
        source=row.source,
        metadata=row.metadata,
    )


@router.post(
    "/dispensaries/suggest",
    response_model=DispensarySuggestResponse,
    status_code=status.HTTP_201_CREATED,
)
def suggest_dispensary(
    payload: DispensarySuggestRequest,
    session: Session = Depends(get_db_session),
) -> DispensarySuggestResponse:
    name_trimmed = payload.name.strip()
    name_norm = name_trimmed.lower()

    existing = session.execute(
        text("SELECT 1 FROM glims_dispensaries WHERE lower(trim(name)) = :name LIMIT 1"),
        {"name": name_norm},
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="dispensary_already_exists")

    ingest_existing = session.execute(
        text(
            """
            SELECT id FROM glims_dispensaries_ingest
            WHERE name_normalized = :name_norm OR sheet_line_number = :line
            LIMIT 1
            """
        ),
        {"name_norm": name_norm, "line": payload.sheet_line_number},
    ).scalar_one_or_none()
    if ingest_existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ingest_entry_already_exists")

    row = session.execute(
        text(
            """
            INSERT INTO glims_dispensaries_ingest (sheet_line_number, name, source)
            VALUES (:line, :name, 'apps_script')
            RETURNING id, name, sheet_line_number, created_at, processed, approved
            """
        ),
        {"line": payload.sheet_line_number, "name": name_trimmed},
    ).one()

    return DispensarySuggestResponse(
        id=row.id,
        name=row.name,
        sheet_line_number=row.sheet_line_number,
        created_at=row.created_at,
        processed=row.processed,
        approved=row.approved,
    )
