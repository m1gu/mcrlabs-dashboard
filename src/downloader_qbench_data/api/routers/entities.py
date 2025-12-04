"""Routes for entity detail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db_session, require_active_user
from ..schemas.entities import OrderDetailResponse, SampleDetailResponse, TestDetailResponse
from ..services import entities as entities_service

router = APIRouter(
    prefix="/entities",
    tags=["entities"],
    dependencies=[Depends(require_active_user)],
)


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
def get_order_detail(
    order_id: int = Path(..., description="Identifier of the order"),
    sla_hours: float = Query(48.0, ge=0.0),
    include_samples: bool = Query(True),
    include_tests: bool = Query(False),
    session: Session = Depends(get_db_session),
) -> OrderDetailResponse:
    result = entities_service.get_order_detail(
        session,
        order_id=order_id,
        sla_hours=sla_hours,
        include_samples=include_samples,
        include_tests=include_tests,
    )
    if not result:
        raise HTTPException(status_code=404, detail="not_found")
    return result


@router.get("/samples/{sample_id}", response_model=SampleDetailResponse)
def get_sample_detail(
    sample_id: int = Path(..., description="Identifier of the sample"),
    full: bool = Query(False, description="Deprecated flag, use /samples/{id}/full"),
    session: Session = Depends(get_db_session),
) -> SampleDetailResponse:
    """Return details for a specific sample."""

    result = entities_service.get_sample_detail(
        session,
        sample_id=sample_id,
        sla_hours=48.0,
        include_tests=False,
        include_batches=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Sample not found")
    return result


@router.get("/samples/{sample_id}/full", response_model=SampleDetailResponse)
def get_sample_detail_full(
    sample_id: int = Path(..., description="Identifier of the sample"),
    sla_hours: float = Query(48.0, ge=0.0),
    include_tests: bool = Query(True),
    include_batches: bool = Query(True),
    session: Session = Depends(get_db_session),
) -> SampleDetailResponse:
    result = entities_service.get_sample_detail(
        session,
        sample_id=sample_id,
        sla_hours=sla_hours,
        include_tests=include_tests,
        include_batches=include_batches,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Sample not found")
    return result


@router.get("/tests/{test_id}", response_model=TestDetailResponse)
def get_test_detail(
    test_id: int = Path(..., description="Identifier of the test"),
    session: Session = Depends(get_db_session),
) -> TestDetailResponse:
    """Return details for a specific test."""

    result = entities_service.get_test_detail(
        session,
        test_id=test_id,
        sla_hours=48.0,
        include_sample=True,
        include_order=True,
        include_batches=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Test not found")
    return result


@router.get("/tests/{test_id}/full", response_model=TestDetailResponse)
def get_test_detail_full(
    test_id: int = Path(..., description="Identifier of the test"),
    sla_hours: float = Query(48.0, ge=0.0),
    include_sample: bool = Query(True),
    include_order: bool = Query(True),
    include_batches: bool = Query(True),
    session: Session = Depends(get_db_session),
) -> TestDetailResponse:
    result = entities_service.get_test_detail(
        session,
        test_id=test_id,
        sla_hours=sla_hours,
        include_sample=include_sample,
        include_order=include_order,
        include_batches=include_batches,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Test not found")
    return result
