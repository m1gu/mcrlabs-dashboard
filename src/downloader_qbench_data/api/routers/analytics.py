"""Routes for operational efficiency analytics."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db_session, require_active_user
from ..schemas.analytics import (
    CustomerAlertsResponse,
    OrdersFunnelResponse,
    OrdersSlowestResponse,
    SlowReportedOrdersResponse,
    OrdersThroughputResponse,
    OverdueOrdersResponse,
    QualityKpisResponse,
    SamplesCycleTimeResponse,
    TestsStateDistributionResponse,
    CustomerOrdersSummaryResponse,
)
from ..services.analytics import (
    get_customer_alerts,
    get_customer_orders_summary,
    get_priority_slowest_reported_orders,
    get_orders_funnel,
    get_overdue_orders,
    get_slowest_orders,
    get_orders_throughput,
    get_quality_kpis,
    get_samples_cycle_time,
    get_tests_state_distribution,
)

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_active_user)],
)


@router.get("/orders/throughput", response_model=OrdersThroughputResponse)
def orders_throughput(
    date_from: Optional[datetime] = Query(
        None, description="Filter orders created on/after this datetime"
    ),
    date_to: Optional[datetime] = Query(
        None, description="Filter orders created on/before this datetime"
    ),
    customer_id: Optional[int] = Query(None),
    interval: str = Query(
        "day",
        description="Aggregation interval (day or week)",
        pattern="^(day|week)$",
    ),
    session: Session = Depends(get_db_session),
) -> OrdersThroughputResponse:
    """Return counts of orders created/completed and completion times by interval."""

    return get_orders_throughput(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        interval=interval,
    )


@router.get("/samples/cycle-time", response_model=SamplesCycleTimeResponse)
def samples_cycle_time(
    date_from: Optional[datetime] = Query(
        None, description="Filter samples completed on/after this datetime"
    ),
    date_to: Optional[datetime] = Query(
        None, description="Filter samples completed on/before this datetime"
    ),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    matrix_type: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    interval: str = Query(
        "day",
        description="Aggregation interval (day or week)",
        pattern="^(day|week)$",
    ),
    session: Session = Depends(get_db_session),
) -> SamplesCycleTimeResponse:
    """Return sample cycle-time statistics grouped by interval and matrix type."""

    return get_samples_cycle_time(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        matrix_type=matrix_type,
        state=state,
        interval=interval,
    )


@router.get("/orders/funnel", response_model=OrdersFunnelResponse)
def orders_funnel(
    date_from: Optional[datetime] = Query(
        None, description="Filter orders created on/after this datetime"
    ),
    date_to: Optional[datetime] = Query(
        None, description="Filter orders created on/before this datetime"
    ),
    customer_id: Optional[int] = Query(None),
    session: Session = Depends(get_db_session),
) -> OrdersFunnelResponse:
    """Return funnel counts for order lifecycle stages."""

    return get_orders_funnel(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
    )


@router.get("/orders/slowest", response_model=OrdersSlowestResponse)
def orders_slowest(
    date_from: Optional[datetime] = Query(
        None, description="Filter orders created on/after this datetime"
    ),
    date_to: Optional[datetime] = Query(
        None, description="Filter orders created on/before this datetime"
    ),
    customer_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(
        10,
        ge=1,
        le=100,
        description="Maximum number of slowest orders to return",
    ),
    session: Session = Depends(get_db_session),
) -> OrdersSlowestResponse:
    """Return the slowest orders ranked by completion time or current age."""

    return get_slowest_orders(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        state=state,
        limit=limit,
    )


@router.get("/priority-orders/slowest", response_model=SlowReportedOrdersResponse)
def priority_orders_slowest(
    date_from: Optional[datetime] = Query(
        None, description="Filter orders reported on/after this datetime"
    ),
    date_to: Optional[datetime] = Query(
        None, description="Filter orders reported on/before this datetime"
    ),
    customer_query: Optional[str] = Query(
        None, description="Customer identifier or name fragment to match"
    ),
    min_open_hours: float = Query(
        0.0,
        ge=0.0,
        description="Only include orders whose open time (created -> reported) meets this threshold",
    ),
    lookback_days: Optional[int] = Query(
        None,
        ge=1,
        le=90,
        description="Number of days before date_to to include when date_from is omitted",
    ),
    limit: int = Query(
        25,
        ge=1,
        le=100,
        description="Maximum number of orders to return",
    ),
    outlier_threshold_hours: Optional[float] = Query(
        120.0,
        ge=0.0,
        description="Highlight rows whose open time exceeds this threshold",
    ),
    session: Session = Depends(get_db_session),
) -> SlowReportedOrdersResponse:
    """Return reported orders ranked by how long they took to complete."""

    return get_priority_slowest_reported_orders(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_query=customer_query,
        min_open_hours=min_open_hours,
        highlight_threshold_hours=outlier_threshold_hours,
        lookback_days=lookback_days,
        limit=limit,
    )


@router.get("/orders/overdue", response_model=OverdueOrdersResponse)
def orders_overdue(
    date_from: Optional[datetime] = Query(None, description="Filter orders created on/after this datetime"),
    date_to: Optional[datetime] = Query(None, description="Filter orders created on/before this datetime"),
    interval: str = Query(
        "week",
        description="Aggregation interval for timeline and heatmap (day or week)",
        pattern="^(day|week)$",
    ),
    min_days_overdue: int = Query(30, ge=0, description="Minimum age in days for an order to be considered overdue"),
    warning_window_days: int = Query(
        5,
        ge=0,
        description="Window in days prior to the overdue threshold to flag warning orders",
    ),
    sla_hours: float = Query(48.0, ge=0.0, description="SLA threshold in hours for overdue comparison"),
    top_limit: int = Query(20, ge=1, le=200, description="Maximum overdue orders to return in the top list"),
    client_limit: int = Query(20, ge=1, le=200, description="Maximum customer aggregates to return"),
    warning_limit: int = Query(20, ge=1, le=200, description="Maximum warning orders to return"),
    session: Session = Depends(get_db_session),
) -> OverdueOrdersResponse:
    """Return analytics for overdue orders."""

    return get_overdue_orders(
        session,
        date_from=date_from,
        date_to=date_to,
        min_days_overdue=min_days_overdue,
        warning_window_days=warning_window_days,
        sla_hours=sla_hours,
        interval=interval,
        top_limit=top_limit,
        client_limit=client_limit,
        warning_limit=warning_limit,
    )


@router.get("/customers/alerts", response_model=CustomerAlertsResponse)
def customers_alerts(
    date_from: Optional[datetime] = Query(None, description="Filter tests created on/after this datetime"),
    date_to: Optional[datetime] = Query(None, description="Filter tests created on/before this datetime"),
    customer_id: Optional[int] = Query(None),
    interval: str = Query(
        "week",
        description="Aggregation interval for heatmap (day or week)",
        pattern="^(day|week)$",
    ),
    sla_hours: float = Query(48.0, ge=0.0),
    min_alert_percentage: float = Query(
        0.1,
        ge=0.0,
        le=1.0,
        description="Minimum ratio required to include a customer in the alerts list",
    ),
    session: Session = Depends(get_db_session),
) -> CustomerAlertsResponse:
    """Return customer alert list and state heatmap for quality monitoring."""

    return get_customer_alerts(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        interval=interval,
        sla_hours=sla_hours,
        min_alert_percentage=min_alert_percentage,
    )


@router.get("/customers/orders/summary", response_model=CustomerOrdersSummaryResponse)
def customers_orders_summary(
    customer_id: Optional[int] = Query(None, description="Customer identifier to summarise"),
    customer_name: Optional[str] = Query(
        None,
        min_length=3,
        description="Customer name or alias to resolve when customer_id is unknown",
    ),
    match_strategy: str = Query(
        "best",
        pattern="^(best|all)$",
        description="Use 'all' to retrieve matches without computing metrics",
    ),
    match_threshold: float = Query(
        0.6,
        ge=0.0,
        le=1.0,
        description="Minimum score required to accept a match when strategy is 'best'",
    ),
    date_from: Optional[datetime] = Query(None, description="Filter orders created on/after this datetime"),
    date_to: Optional[datetime] = Query(None, description="Filter orders created on/before this datetime"),
    sla_hours: float = Query(48.0, ge=0.0, description="SLA threshold in hours"),
    include_samples: bool = Query(False, description="Include aggregates for pending samples"),
    include_tests: bool = Query(False, description="Include aggregates for pending tests"),
    limit_orders: int = Query(20, ge=1, le=100, description="Maximum number of open orders to list"),
    session: Session = Depends(get_db_session),
) -> CustomerOrdersSummaryResponse:
    """Return customer-focused order summary with optional alias lookup."""

    try:
        return get_customer_orders_summary(
            session,
            customer_id=customer_id,
            customer_name=customer_name,
            match_strategy=match_strategy,
            match_threshold=match_threshold,
            date_from=date_from,
            date_to=date_to,
            sla_hours=sla_hours,
            include_samples=include_samples,
            include_tests=include_tests,
            limit_orders=limit_orders,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tests/state-distribution", response_model=TestsStateDistributionResponse)
def tests_state_distribution(
    date_from: Optional[datetime] = Query(None, description="Filter tests created on/after this datetime"),
    date_to: Optional[datetime] = Query(None, description="Filter tests created on/before this datetime"),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    interval: str = Query(
        "week",
        description="Aggregation interval for stacked series (day or week)",
        pattern="^(day|week)$",
    ),
    session: Session = Depends(get_db_session),
) -> TestsStateDistributionResponse:
    """Return stacked distribution of test states over time."""

    return get_tests_state_distribution(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        interval=interval,
    )


@router.get("/kpis/quality", response_model=QualityKpisResponse)
def quality_kpis(
    date_from: Optional[datetime] = Query(None, description="Filter entities created on/after this datetime"),
    date_to: Optional[datetime] = Query(None, description="Filter entities created on/before this datetime"),
    customer_id: Optional[int] = Query(None),
    order_id: Optional[int] = Query(None),
    sla_hours: float = Query(48.0, ge=0.0),
    session: Session = Depends(get_db_session),
) -> QualityKpisResponse:
    """Return aggregate quality KPIs for tests and orders."""

    return get_quality_kpis(
        session,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        sla_hours=sla_hours,
    )
