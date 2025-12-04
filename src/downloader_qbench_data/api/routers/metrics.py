"""Routes for metrics endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db_session, require_active_user
from ..schemas.metrics import (
    DailyActivityResponse,
    MetricsFiltersResponse,
    MetricsSummaryResponse,
    NewCustomersResponse,
    ReportsOverviewResponse,
    SamplesOverviewResponse,
    TestsLabelDistributionResponse,
    TestsOverviewResponse,
    TestsTATBreakdownResponse,
    TestsTATDailyResponse,
    TestsTATResponse,
    TopCustomersResponse,
    SyncStatusResponse,
)
from ..services.metrics import (
    get_daily_activity,
    get_metrics_filters,
    get_metrics_summary,
    get_new_customers,
    get_reports_overview,
    get_samples_overview,
    get_tests_label_distribution,
    get_tests_overview,
    get_tests_tat,
    get_tests_tat_breakdown,
    get_tests_tat_daily,
    get_top_customers_by_tests,
    get_sync_status,
)

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(require_active_user)],
)


@router.get("/summary", response_model=MetricsSummaryResponse)
def metrics_summary(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    sla_hours: float = Query(48.0, ge=0),
    session: Session = Depends(get_db_session),
) -> MetricsSummaryResponse:
    """Return KPI summary for the selected range."""

    return get_metrics_summary(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        sla_hours=sla_hours,
    )


@router.get("/activity/daily", response_model=DailyActivityResponse)
def daily_activity(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    compare_previous: bool = Query(
        False, description="Include data for the matching previous period"
    ),
    session: Session = Depends(get_db_session),
) -> DailyActivityResponse:
    """Return daily counts for samples and tests."""

    return get_daily_activity(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        compare_previous=compare_previous,
    )


@router.get("/customers/new", response_model=NewCustomersResponse)
def new_customers(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(10, ge=1),
    session: Session = Depends(get_db_session),
) -> NewCustomersResponse:
    """Return customers created within the selected range."""

    return get_new_customers(
        session,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get("/customers/top-tests", response_model=TopCustomersResponse)
def top_customers_by_tests(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(10, ge=1),
    session: Session = Depends(get_db_session),
) -> TopCustomersResponse:
    """Return top customers ranked by tests in the range."""

    return get_top_customers_by_tests(
        session,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get("/reports/overview", response_model=ReportsOverviewResponse)
def reports_overview(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    sla_hours: float = Query(48.0, ge=0),
    session: Session = Depends(get_db_session),
) -> ReportsOverviewResponse:
    """Return report counts inside/outside SLA."""

    return get_reports_overview(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        sla_hours=sla_hours,
    )


@router.get("/tests/tat-daily", response_model=TestsTATDailyResponse)
def tests_tat_daily(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    sla_hours: float = Query(48.0, ge=0),
    moving_average_window: int = Query(7, ge=1),
    session: Session = Depends(get_db_session),
) -> TestsTATDailyResponse:
    """Return daily TAT statistics including moving averages."""

    return get_tests_tat_daily(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        sla_hours=sla_hours,
        moving_average_window=moving_average_window,
    )


@router.get("/samples/overview", response_model=SamplesOverviewResponse)
def samples_overview(
    date_from: Optional[datetime] = Query(None, description="Filter samples created after this datetime"),
    date_to: Optional[datetime] = Query(None, description="Filter samples created before this datetime"),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    session: Session = Depends(get_db_session),
) -> SamplesOverviewResponse:
    """Return aggregated metrics for samples."""

    return get_samples_overview(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
    )


@router.get("/tests/overview", response_model=TestsOverviewResponse)
def tests_overview(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    batch_id: Optional[int] = Query(None),
    session: Session = Depends(get_db_session),
) -> TestsOverviewResponse:
    """Return aggregated metrics for tests."""

    return get_tests_overview(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        batch_id=batch_id,
    )


@router.get("/tests/tat", response_model=TestsTATResponse)
def tests_tat(
    date_created_from: Optional[datetime] = Query(None),
    date_created_to: Optional[datetime] = Query(None),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    group_by: Optional[str] = Query(
        None,
        pattern="^(day|week)$",
        description="Optional grouping interval for time series data",
    ),
    session: Session = Depends(get_db_session),
) -> TestsTATResponse:
    """Return turnaround time metrics for tests."""

    return get_tests_tat(
        session,
        date_created_from=date_created_from,
        date_created_to=date_created_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        group_by=group_by,
    )


@router.get("/tests/tat-breakdown", response_model=TestsTATBreakdownResponse)
def tests_tat_breakdown(
    date_created_from: Optional[datetime] = Query(None),
    date_created_to: Optional[datetime] = Query(None),
    session: Session = Depends(get_db_session),
) -> TestsTATBreakdownResponse:
    """Return TAT metrics broken down by label."""

    return get_tests_tat_breakdown(
        session,
        date_created_from=date_created_from,
        date_created_to=date_created_to,
    )


@router.get("/common/filters", response_model=MetricsFiltersResponse)
def metrics_filters(
    session: Session = Depends(get_db_session),
) -> MetricsFiltersResponse:
    """Return values for populating dashboard filters."""

    return get_metrics_filters(session)


@router.get("/tests/label-distribution", response_model=TestsLabelDistributionResponse)
def tests_label_distribution(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    session: Session = Depends(get_db_session),
) -> TestsLabelDistributionResponse:
    """Return counts of predefined test labels for the selected creation range."""

    return get_tests_label_distribution(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
    )


@router.get("/sync/status", response_model=SyncStatusResponse)
def sync_status(
    entity: str = Query(
        "tests",
        description="Entity name from sync_checkpoints table",
    ),
    session: Session = Depends(get_db_session),
) -> SyncStatusResponse:
    """Return last sync timestamp for a given entity."""

    return get_sync_status(session, entity=entity)
