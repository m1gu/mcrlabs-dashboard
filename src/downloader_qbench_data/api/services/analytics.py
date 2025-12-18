"""Service helpers for analytics endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import Text, and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from downloader_qbench_data.storage import BannedEntity, Customer, MetrcSampleStatus, Order, Sample, Test
from downloader_qbench_data.bans import is_banned
from ..schemas.analytics import (
    CustomerAlertItem,
    CustomerAlertsResponse,
    CustomerHeatmapPoint,
    OrdersFunnelResponse,
    OrdersFunnelStage,
    OrdersSlowestResponse,
    OrdersThroughputPoint,
    OrdersThroughputResponse,
    OrdersThroughputTotals,
    OverdueClientSummary,
    OverdueHeatmapCell,
    OverdueOrderItem,
    OverdueSampleDetail,
    OverdueTestDetail,
    OverdueOrdersKpis,
    OverdueOrdersResponse,
    OverdueStateBreakdown,
    OverdueTimelinePoint,
    ReadyToReportSampleItem,
    MetrcSampleStatusItem,
    QualityKpiOrders,
    QualityKpiTests,
    QualityKpisResponse,
    SlowOrderItem,
    SlowReportedOrderItem,
    SlowReportedOrdersResponse,
    SlowReportedOrdersStats,
    SamplesCycleMatrixItem,
    SamplesCycleTimePoint,
    SamplesCycleTimeResponse,
    SamplesCycleTimeTotals,
    TestStateBucket,
    TestStatePoint,
    TestsStateDistributionResponse,
)
from .metrics import _apply_test_filters, _daterange_conditions  # reuse helpers for consistency

_VALID_INTERVALS = {"day", "week"}
_MATCH_STRATEGIES = {"best", "all"}
_WARNING_RATIO = 0.75


def _normalise_interval(interval: Optional[str]) -> str:
    if not interval:
        return "day"
    interval_lower = interval.lower()
    if interval_lower not in _VALID_INTERVALS:
        raise ValueError(f"Unsupported interval '{interval}'. Allowed values: {sorted(_VALID_INTERVALS)}")
    return interval_lower


def _epoch_hours(expr) -> any:
    return func.extract("epoch", expr) / 3600.0


def _format_open_time_label(hours: Optional[float]) -> str:
    if hours is None:
        return "--"
    clamped = max(0.0, float(hours))
    total_hours = int(round(clamped))
    days, remaining_hours = divmod(total_hours, 24)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    parts.append(f"{remaining_hours}h")
    return " ".join(parts)


def _convert_period(period_value) -> datetime.date:
    if period_value is None:
        raise ValueError("Aggregation period cannot be null")
    if hasattr(period_value, "date"):
        return period_value.date()
    return period_value  # Already a date


def _normalise_match_strategy(strategy: Optional[str]) -> str:
    if not strategy:
        return "best"
    value = strategy.lower()
    if value not in _MATCH_STRATEGIES:
        raise ValueError(f"Unsupported match_strategy '{strategy}'. Allowed values: best, all")
    return value


def _order_visibility_conditions() -> list:
    order_banned = exists().where(
        (BannedEntity.entity_type == literal("order")) & (BannedEntity.entity_id == Order.id)
    )
    customer_banned = exists().where(
        (BannedEntity.entity_type == literal("customer")) & (BannedEntity.entity_id == Order.customer_account_id)
    )
    return [~order_banned, ~customer_banned]


def _sample_visibility_conditions() -> list:
    customer_subq = (
        select(Order.customer_account_id)
        .where(Order.id == Sample.order_id)
        .correlate(Sample)
        .scalar_subquery()
    )
    sample_banned = exists().where(
        (BannedEntity.entity_type == literal("sample")) & (BannedEntity.entity_id == Sample.id)
    )
    order_banned = exists().where(
        (BannedEntity.entity_type == literal("order")) & (BannedEntity.entity_id == Sample.order_id)
    )
    customer_banned = exists().where(
        (BannedEntity.entity_type == literal("customer")) & (BannedEntity.entity_id == customer_subq)
    )
    return [~sample_banned, ~order_banned, ~customer_banned]


def _test_visibility_conditions() -> list:
    sample_order_subq = (
        select(Sample.order_id)
        .where(Sample.id == Test.sample_id)
        .correlate(Test)
        .scalar_subquery()
    )
    customer_subq = (
        select(Order.customer_account_id)
        .join(Sample, Sample.order_id == Order.id)
        .where(Sample.id == Test.sample_id)
        .correlate(Test)
        .scalar_subquery()
    )
    test_banned = exists().where(
        (BannedEntity.entity_type == literal("test")) & (BannedEntity.entity_id == Test.id)
    )
    sample_banned = exists().where(
        (BannedEntity.entity_type == literal("sample")) & (BannedEntity.entity_id == Test.sample_id)
    )
    order_banned = exists().where(
        (BannedEntity.entity_type == literal("order")) & (BannedEntity.entity_id == sample_order_subq)
    )
    customer_banned = exists().where(
        (BannedEntity.entity_type == literal("customer")) & (BannedEntity.entity_id == customer_subq)
    )
    return [~test_banned, ~sample_banned, ~order_banned, ~customer_banned]


def get_orders_throughput(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    interval: Optional[str] = "day",
) -> OrdersThroughputResponse:
    """Aggregate orders created/completed counts and completion times."""

    interval_value = _normalise_interval(interval)

    created_conditions = _daterange_conditions(Order.date_created, date_from, date_to)
    completed_conditions = _daterange_conditions(Order.date_completed, date_from, date_to)
    if customer_id is not None:
        created_conditions.append(Order.customer_account_id == customer_id)
        completed_conditions.append(Order.customer_account_id == customer_id)

    created_stmt = (
        select(
            func.date_trunc(interval_value, Order.date_created).label("period"),
            func.count().label("created_count"),
        )
        .where(Order.date_created.isnot(None), *created_conditions)
        .group_by("period")
        .order_by("period")
    )

    duration_expr = _epoch_hours(Order.date_completed - Order.date_created)
    completed_stmt = (
        select(
            func.date_trunc(interval_value, Order.date_completed).label("period"),
            func.count().label("completed_count"),
            func.avg(duration_expr).label("avg_hours"),
            func.percentile_cont(0.5).within_group(duration_expr).label("median_hours"),
        )
        .where(Order.date_completed.isnot(None), Order.date_created.isnot(None), *completed_conditions)
        .group_by("period")
        .order_by("period")
    )

    created_map: Dict[datetime.date, int] = {}
    for row in session.execute(created_stmt):
        period = _convert_period(row.period)
        created_map[period] = int(row.created_count or 0)

    completed_map: Dict[datetime.date, Tuple[int, Optional[float], Optional[float]]] = {}
    for row in session.execute(completed_stmt):
        period = _convert_period(row.period)
        avg_hours = float(row.avg_hours) if row.avg_hours is not None else None
        median_hours = float(row.median_hours) if row.median_hours is not None else None
        completed_map[period] = (int(row.completed_count or 0), avg_hours, median_hours)

    periods = sorted(set(created_map) | set(completed_map))
    points: list[OrdersThroughputPoint] = []
    for period in periods:
        completed_count, avg_hours, median_hours = completed_map.get(period, (0, None, None))
        points.append(
            OrdersThroughputPoint(
                period_start=period,
                orders_created=created_map.get(period, 0),
                orders_completed=completed_count,
                average_completion_hours=avg_hours,
                median_completion_hours=median_hours,
            )
        )

    # Totals
    total_created = sum(created_map.values())
    total_completed = sum(value[0] for value in completed_map.values())
    total_duration_stmt = (
        select(
            func.count().label("completed"),
            func.avg(duration_expr).label("avg_hours"),
            func.percentile_cont(0.5).within_group(duration_expr).label("median_hours"),
        )
        .where(Order.date_completed.isnot(None), Order.date_created.isnot(None), *completed_conditions)
    )
    total_row = session.execute(total_duration_stmt).one()
    total_avg = float(total_row.avg_hours) if total_row.avg_hours is not None else None
    total_median = float(total_row.median_hours) if total_row.median_hours is not None else None

    response = OrdersThroughputResponse(
        interval=interval_value,
        points=points,
        totals=OrdersThroughputTotals(
            orders_created=total_created,
            orders_completed=total_completed,
            average_completion_hours=total_avg,
            median_completion_hours=total_median,
        ),
    )
    return response


def _sample_cycle_conditions(
    *,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    customer_id: Optional[int],
    order_id: Optional[int],
    matrix_type: Optional[str],
    state: Optional[str],
) -> Tuple[list, bool]:
    conditions = _daterange_conditions(Sample.completed_date, date_from, date_to)
    join_order = False
    if customer_id is not None:
        join_order = True
        conditions.append(Order.customer_account_id == customer_id)
    if order_id is not None:
        conditions.append(Sample.order_id == order_id)
    if matrix_type:
        conditions.append(Sample.matrix_type == matrix_type)
    if state:
        conditions.append(Sample.state == state)
    return conditions, join_order


def get_samples_cycle_time(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    matrix_type: Optional[str] = None,
    state: Optional[str] = None,
    interval: Optional[str] = "day",
) -> SamplesCycleTimeResponse:
    """Return cycle time metrics for samples."""

    interval_value = _normalise_interval(interval)
    conditions, join_order = _sample_cycle_conditions(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        matrix_type=matrix_type,
        state=state,
    )

    stmt = (
        select(
            func.date_trunc(interval_value, Sample.completed_date).label("period"),
            func.count().label("completed_samples"),
            func.avg(_epoch_hours(Sample.completed_date - Sample.date_created)).label("avg_hours"),
            func.percentile_cont(0.5).within_group(_epoch_hours(Sample.completed_date - Sample.date_created)).label(
                "median_hours"
            ),
        )
        .where(
            Sample.completed_date.isnot(None),
            Sample.date_created.isnot(None),
            *conditions,
        )
        .group_by("period")
        .order_by("period")
    )
    if join_order:
        stmt = stmt.join(Order, Order.id == Sample.order_id)

    points: list[SamplesCycleTimePoint] = []
    result = session.execute(stmt)
    for row in result:
        period = _convert_period(row.period)
        avg_hours = float(row.avg_hours) if row.avg_hours is not None else None
        median_hours = float(row.median_hours) if row.median_hours is not None else None
        points.append(
            SamplesCycleTimePoint(
                period_start=period,
                completed_samples=int(row.completed_samples or 0),
                average_cycle_hours=avg_hours,
                median_cycle_hours=median_hours,
            )
        )

    totals_stmt = (
        select(
            func.count().label("completed_samples"),
            func.avg(_epoch_hours(Sample.completed_date - Sample.date_created)).label("avg_hours"),
            func.percentile_cont(0.5).within_group(_epoch_hours(Sample.completed_date - Sample.date_created)).label(
                "median_hours"
            ),
        )
        .where(
            Sample.completed_date.isnot(None),
            Sample.date_created.isnot(None),
            *conditions,
        )
    )
    if join_order:
        totals_stmt = totals_stmt.join(Order, Order.id == Sample.order_id)
    totals_row = session.execute(totals_stmt).one()
    totals = SamplesCycleTimeTotals(
        completed_samples=int(totals_row.completed_samples or 0),
        average_cycle_hours=float(totals_row.avg_hours) if totals_row.avg_hours is not None else None,
        median_cycle_hours=float(totals_row.median_hours) if totals_row.median_hours is not None else None,
    )

    matrix_stmt = (
        select(
            func.coalesce(Sample.matrix_type, "Unknown").label("matrix_type"),
            func.count().label("completed_samples"),
            func.avg(_epoch_hours(Sample.completed_date - Sample.date_created)).label("avg_hours"),
        )
        .where(
            Sample.completed_date.isnot(None),
            Sample.date_created.isnot(None),
            *conditions,
        )
        .group_by("matrix_type")
        .order_by("matrix_type")
    )
    if join_order:
        matrix_stmt = matrix_stmt.join(Order, Order.id == Sample.order_id)

    by_matrix: list[SamplesCycleMatrixItem] = []
    for row in session.execute(matrix_stmt):
        avg_hours = float(row.avg_hours) if row.avg_hours is not None else None
        by_matrix.append(
            SamplesCycleMatrixItem(
                matrix_type=row.matrix_type,
                completed_samples=int(row.completed_samples or 0),
                average_cycle_hours=avg_hours,
            )
        )

    return SamplesCycleTimeResponse(
        interval=interval_value,
        points=points,
        totals=totals,
        by_matrix_type=by_matrix,
    )


def get_orders_funnel(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
) -> OrdersFunnelResponse:
    """Return counts for each stage of the order lifecycle."""

    created_conditions = _daterange_conditions(Order.date_created, date_from, date_to)
    received_conditions = _daterange_conditions(Order.date_received, date_from, date_to)
    completed_conditions = _daterange_conditions(Order.date_completed, date_from, date_to)
    reported_conditions = _daterange_conditions(Order.date_order_reported, date_from, date_to)

    if customer_id is not None:
        created_conditions.append(Order.customer_account_id == customer_id)
        received_conditions.append(Order.customer_account_id == customer_id)
        completed_conditions.append(Order.customer_account_id == customer_id)
        reported_conditions.append(Order.customer_account_id == customer_id)

    def _count(column_conditions: Iterable, column_is_not_null) -> int:
        stmt = (
            select(func.count())
            .select_from(Order)
            .where(column_is_not_null, *column_conditions)
        )
        return int(session.execute(stmt).scalar_one() or 0)

    total_created = _count(created_conditions, Order.date_created.isnot(None))
    received = _count(received_conditions, Order.date_received.isnot(None))
    completed = _count(completed_conditions, Order.date_completed.isnot(None))
    reported = _count(reported_conditions, Order.date_order_reported.isnot(None))

    on_hold_conditions = list(created_conditions)
    on_hold_conditions.append(Order.state == "ON HOLD")
    on_hold = _count(on_hold_conditions, Order.date_created.isnot(None))

    stages = [
        OrdersFunnelStage(stage="created", count=total_created),
        OrdersFunnelStage(stage="received", count=received),
        OrdersFunnelStage(stage="completed", count=completed),
        OrdersFunnelStage(stage="reported", count=reported),
        OrdersFunnelStage(stage="on_hold", count=on_hold),
    ]

    return OrdersFunnelResponse(total_orders=total_created, stages=stages)


def get_slowest_orders(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    state: Optional[str] = None,
    limit: int = 10,
) -> OrdersSlowestResponse:
    """Return slowest orders by completion time or current age."""

    effective_limit = max(1, min(limit, 100))

    conditions = _daterange_conditions(Order.date_created, date_from, date_to)
    conditions.append(Order.date_created.isnot(None))
    conditions.extend(_order_visibility_conditions())
    if customer_id is not None:
        conditions.append(Order.customer_account_id == customer_id)
    if state:
        conditions.append(Order.state == state)

    reference_expr = literal(date_to) if date_to else func.now()
    completion_expr = _epoch_hours(Order.date_completed - Order.date_created)
    age_expr = func.greatest(_epoch_hours(reference_expr - Order.date_created), literal(0.0))
    sort_key = func.coalesce(completion_expr, age_expr)

    stmt = (
        select(
            Order.id.label("order_id"),
            Order.customer_account_id.label("customer_id"),
            func.coalesce(Order.custom_formatted_id, func.concat("order-", Order.id)).label("order_reference"),
            Customer.name.label("customer_name"),
            Order.state.label("state"),
            Order.date_created.label("date_created"),
            Order.date_completed.label("date_completed"),
            completion_expr.label("completion_hours"),
            age_expr.label("age_hours"),
        )
        .select_from(Order)
        .join(Customer, Customer.id == Order.customer_account_id, isouter=True)
        .where(*conditions)
        .order_by(sort_key.desc(), Order.date_created.desc())
        .limit(effective_limit)
    )

    rows = session.execute(stmt)
    items: list[SlowOrderItem] = []
    for row in rows:
        if is_banned(session, "order", int(row.order_id)) or is_banned(session, "customer", int(row.customer_id)):
            continue
        completion_hours = float(row.completion_hours) if row.completion_hours is not None else None
        age_hours = float(row.age_hours) if row.age_hours is not None else 0.0
        items.append(
            SlowOrderItem(
                order_id=row.order_id,
                order_reference=row.order_reference,
                customer_name=row.customer_name,
                state=row.state,
                completion_hours=completion_hours,
                age_hours=age_hours,
                date_created=row.date_created,
                date_completed=row.date_completed,
            )
        )

    return OrdersSlowestResponse(items=items)


def get_overdue_orders(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    min_days_overdue: int = 30,
    warning_window_days: int = 5,
    sla_hours: float = 48.0,
    interval: Optional[str] = "week",
    top_limit: int = 20,
    client_limit: int = 20,
    warning_limit: int = 20,
) -> OverdueOrdersResponse:
    """Aggregate analytics for overdue orders."""

    minimum_days = max(0, int(min_days_overdue))
    warning_days = max(0, int(warning_window_days))
    interval_value = _normalise_interval(interval)
    sla_hours_value = max(0.0, float(sla_hours))

    base_conditions = _daterange_conditions(Order.date_created, date_from, date_to)
    base_conditions.append(Order.date_created.isnot(None))
    base_conditions.extend(_order_visibility_conditions())
    active_conditions = list(base_conditions)
    active_conditions.append(or_(Order.state.is_(None), Order.state != "REPORTED"))

    reference_expr = literal(date_to) if date_to else func.now()
    open_hours_expr = func.extract("epoch", reference_expr - Order.date_created) / 3600.0
    overdue_hours_threshold = float(minimum_days) * 24.0
    warning_lower_hours = float(max(0, minimum_days - warning_days)) * 24.0
    warning_upper_hours = overdue_hours_threshold

    overdue_conditions = list(active_conditions)
    overdue_conditions.append(open_hours_expr >= overdue_hours_threshold)

    active_count_stmt = select(func.count()).select_from(Order).where(*active_conditions)
    active_count = int(session.execute(active_count_stmt).scalar_one() or 0)

    kpi_stmt = (
        select(
            func.count().label("total"),
            func.avg(open_hours_expr).label("avg_hours"),
            func.max(open_hours_expr).label("max_hours"),
            func.sum(case((open_hours_expr > sla_hours_value, 1), else_=0)).label("beyond_sla"),
        )
        .select_from(Order)
        .where(*overdue_conditions)
    )
    kpi_row = session.execute(kpi_stmt).one()
    total_overdue = int(kpi_row.total or 0)
    avg_hours = float(kpi_row.avg_hours) if kpi_row.avg_hours is not None else None
    max_hours = float(kpi_row.max_hours) if kpi_row.max_hours is not None else None
    beyond_sla = int(kpi_row.beyond_sla or 0)
    within_sla = max(total_overdue - beyond_sla, 0)
    percent_overdue_vs_active = float(total_overdue) / float(active_count) if active_count else 0.0

    top_stmt = (
        select(
            Order.id.label("order_id"),
            Order.custom_formatted_id,
            Order.customer_account_id.label("customer_id"),
            Customer.name.label("customer_name"),
            Order.state,
            Order.date_created,
            open_hours_expr.label("open_hours"),
        )
        .select_from(Order)
        .join(Customer, Customer.id == Order.customer_account_id, isouter=True)
        .where(*overdue_conditions)
        .order_by(open_hours_expr.desc())
        .limit(max(1, min(top_limit, 200)))
    )
    top_rows = list(session.execute(top_stmt))
    order_ids = [row.order_id for row in top_rows]

    total_samples_map: Dict[int, int] = {}
    incomplete_samples_map: Dict[int, list[OverdueSampleDetail]] = {}

    if order_ids:
        total_samples_stmt = (
            select(
                Sample.order_id.label("order_id"),
                func.count(Sample.id).label("total_samples"),
            )
            .select_from(Sample)
            .where(Sample.order_id.in_(order_ids), *_sample_visibility_conditions())
            .group_by(Sample.order_id)
        )
        for row in session.execute(total_samples_stmt):
            total_samples_map[int(row.order_id)] = int(row.total_samples or 0)

        sample_info_stmt = (
            select(
                Sample.id.label("sample_id"),
                Sample.order_id.label("order_id"),
                Sample.custom_formatted_id.label("sample_custom_id"),
                Sample.sample_name.label("sample_name"),
                Sample.matrix_type.label("matrix_type"),
            )
            .where(Sample.order_id.in_(order_ids), *_sample_visibility_conditions())
            .order_by(Sample.order_id, Sample.id)
        )
        sample_info_map: Dict[int, Any] = {}
        for row in session.execute(sample_info_stmt):
            sample_info_map[int(row.sample_id)] = row

        assay_stats_stmt = (
            select(
                Sample.id.label("sample_id"),
                func.coalesce(Test.label_abbr, literal("--")).label("assay"),
                func.count(Test.id).label("total_tests"),
                func.sum(case((Test.state == "REPORTED", 1), else_=0)).label("reported_tests"),
            )
            .select_from(Test)
            .join(Sample, Sample.id == Test.sample_id)
            .where(Sample.order_id.in_(order_ids), *_test_visibility_conditions())
            .group_by(Sample.id, func.coalesce(Test.label_abbr, literal("--")))
        )

        total_tests_per_sample: Dict[int, int] = {}
        pending_assays_map: Dict[int, set[str]] = {}
        incomplete_tests_per_sample: Dict[int, int] = {}

        for row in session.execute(assay_stats_stmt):
            sample_id = int(row.sample_id)
            assay = row.assay or "--"
            total_tests = int(row.total_tests or 0)
            reported_tests = int(row.reported_tests or 0)

            total_tests_per_sample[sample_id] = total_tests_per_sample.get(sample_id, 0) + total_tests
            if reported_tests <= 0:
                pending_assays = pending_assays_map.setdefault(sample_id, set())
                pending_assays.add(assay)
                incomplete_tests_per_sample[sample_id] = incomplete_tests_per_sample.get(sample_id, 0) + total_tests

        tests_stmt = (
            select(
                Sample.order_id.label("order_id"),
                Sample.id.label("sample_id"),
                Test.id.label("test_id"),
                Test.label_abbr,
                Test.state,
            )
            .select_from(Test)
            .join(Sample, Sample.id == Test.sample_id)
            .where(Sample.order_id.in_(order_ids), *_test_visibility_conditions())
            .order_by(Sample.order_id, Sample.id, Test.id)
        )
        sample_tests_map: Dict[tuple[int, int], Dict[str, Dict[str, Any]]] = {}
        for row in session.execute(tests_stmt):
            sample_id = int(row.sample_id)
            pending_assays = pending_assays_map.get(sample_id)
            if not pending_assays:
                continue
            assay_key = row.label_abbr or "--"
            if assay_key not in pending_assays:
                continue
            if row.state == "REPORTED":
                continue
            key = (int(row.order_id), sample_id)
            label_dict = sample_tests_map.setdefault(key, {})
            entry = label_dict.setdefault(
                assay_key,
                {
                    "primary_id": row.test_id,
                    "test_ids": [],
                    "states": set(),
                    "label": row.label_abbr,
                },
            )
            entry["test_ids"].append(row.test_id)
            entry["states"].add((row.state or "--").upper())
            if row.test_id < entry["primary_id"]:
                entry["primary_id"] = row.test_id

        def _state_priority(value: str) -> tuple[int, str]:
            upper = value.upper()
            if upper == "REPORTED":
                return (0, upper)
            if upper == "NOT REPORTABLE":
                return (2, upper)
            return (1, upper)

        for sample_id, assays in pending_assays_map.items():
            info = sample_info_map.get(sample_id)
            if not info:
                continue
            order_id = int(info.order_id)
            key = (order_id, sample_id)
            label_dict = sample_tests_map.get(key, {})
            tests: list[OverdueTestDetail] = []
            for assay_key, entry in label_dict.items():
                states_sorted = sorted(entry["states"], key=_state_priority)
                tests.append(
                    OverdueTestDetail(
                        primary_test_id=int(entry["primary_id"]),
                        test_ids=sorted(entry["test_ids"]),
                        label_abbr=entry["label"],
                        states=states_sorted,
                    )
                )
            tests.sort(key=lambda item: (item.label_abbr or "", item.primary_test_id))
            sample_detail = OverdueSampleDetail(
                sample_id=sample_id,
                sample_custom_id=info.sample_custom_id,
                sample_name=info.sample_name,
                matrix_type=info.matrix_type,
                total_tests=total_tests_per_sample.get(sample_id, 0),
                incomplete_tests=incomplete_tests_per_sample.get(sample_id, len(tests)),
                tests=tests,
            )
            incomplete_samples_map.setdefault(order_id, []).append(sample_detail)

    top_orders = []
    for row in top_rows:
        order_id = int(row.order_id)
        samples = incomplete_samples_map.get(order_id, [])
        total_samples = total_samples_map.get(order_id, 0)
        top_orders.append(
            OverdueOrderItem(
                order_id=order_id,
                custom_formatted_id=row.custom_formatted_id,
                customer_id=row.customer_id,
                customer_name=row.customer_name,
                state=row.state,
                date_created=row.date_created,
                open_hours=float(row.open_hours) if row.open_hours is not None else 0.0,
                total_samples=total_samples,
                incomplete_sample_count=len(samples),
                incomplete_samples=samples,
            )
        )

    clients_stmt = (
        select(
            Customer.id.label("customer_id"),
            Customer.name.label("customer_name"),
            func.count(Order.id).label("overdue_orders"),
            func.sum(open_hours_expr).label("total_open_hours"),
            func.avg(open_hours_expr).label("avg_open_hours"),
            func.max(open_hours_expr).label("max_open_hours"),
        )
        .select_from(Order)
        .join(Customer, Customer.id == Order.customer_account_id, isouter=True)
        .where(*overdue_conditions)
        .group_by(Customer.id, Customer.name)
        .order_by(func.sum(open_hours_expr).desc())
        .limit(max(1, min(client_limit, 200)))
    )
    clients = []
    for row in session.execute(clients_stmt):
        clients.append(
            OverdueClientSummary(
                customer_id=row.customer_id,
                customer_name=row.customer_name,
                overdue_orders=int(row.overdue_orders or 0),
                total_open_hours=float(row.total_open_hours or 0.0),
                average_open_hours=float(row.avg_open_hours) if row.avg_open_hours is not None else None,
                max_open_hours=float(row.max_open_hours) if row.max_open_hours is not None else None,
            )
        )

    warning_orders: list[OverdueOrderItem] = []
    if warning_days > 0 and warning_lower_hours < warning_upper_hours:
        warning_conditions = list(active_conditions)
        warning_conditions.append(open_hours_expr >= warning_lower_hours)
        warning_conditions.append(open_hours_expr < warning_upper_hours)

        warning_stmt = (
            select(
                Order.id.label("order_id"),
                Order.custom_formatted_id,
                Order.customer_account_id.label("customer_id"),
                Customer.name.label("customer_name"),
                Order.state,
                Order.date_created,
                open_hours_expr.label("open_hours"),
            )
            .select_from(Order)
            .join(Customer, Customer.id == Order.customer_account_id, isouter=True)
            .where(*warning_conditions)
            .order_by(open_hours_expr.desc())
            .limit(max(1, min(warning_limit, 200)))
        )
        for row in session.execute(warning_stmt):
            warning_orders.append(
                OverdueOrderItem(
                    order_id=row.order_id,
                    custom_formatted_id=row.custom_formatted_id,
                    customer_id=row.customer_id,
                    customer_name=row.customer_name,
                    state=row.state,
                    date_created=row.date_created,
                    open_hours=float(row.open_hours) if row.open_hours is not None else 0.0,
                )
            )

    period_expr = func.date_trunc(interval_value, Order.date_created).label("period")
    timeline_stmt = (
        select(
            period_expr,
            func.count(Order.id).label("overdue_orders"),
        )
        .select_from(Order)
        .where(*overdue_conditions)
        .group_by(period_expr)
        .order_by(period_expr)
    )
    timeline = [
        OverdueTimelinePoint(
            period_start=_convert_period(row.period),
            overdue_orders=int(row.overdue_orders or 0),
        )
        for row in session.execute(timeline_stmt)
    ]

    heatmap_stmt = (
        select(
            Customer.id.label("customer_id"),
            Customer.name.label("customer_name"),
            period_expr,
            func.count(Order.id).label("overdue_orders"),
        )
        .select_from(Order)
        .join(Customer, Customer.id == Order.customer_account_id, isouter=True)
        .where(*overdue_conditions)
        .group_by(Customer.id, Customer.name, period_expr)
        .order_by(Customer.name, period_expr)
    )
    heatmap = [
        OverdueHeatmapCell(
            customer_id=row.customer_id,
            customer_name=row.customer_name,
            period_start=_convert_period(row.period),
            overdue_orders=int(row.overdue_orders or 0),
        )
        for row in session.execute(heatmap_stmt)
    ]

    state_stmt = (
        select(
            Order.state,
            func.count(Order.id).label("count"),
        )
        .select_from(Order)
        .where(*overdue_conditions)
        .group_by(Order.state)
    )
    breakdown = []
    for row in session.execute(state_stmt):
        count = int(row.count or 0)
        ratio = float(count) / float(total_overdue) if total_overdue else 0.0
        breakdown.append(
            OverdueStateBreakdown(
                state=row.state,
                count=count,
                ratio=ratio,
            )
        )
    breakdown.sort(key=lambda item: item.count, reverse=True)

    kpis = OverdueOrdersKpis(
        total_overdue=total_overdue,
        average_open_hours=avg_hours,
        max_open_hours=max_hours,
        percent_overdue_vs_active=percent_overdue_vs_active,
        overdue_beyond_sla=beyond_sla,
        overdue_within_sla=within_sla,
    )

    # Window for METRC samples: use provided date range when available; otherwise default lookback 30 days
    reference_dt = date_to if date_to else datetime.utcnow()
    if reference_dt.tzinfo is not None:
        reference_dt = reference_dt.astimezone(timezone.utc).replace(tzinfo=None)
    window_start = date_from if date_from else reference_dt - timedelta(days=30)
    status_window_start = window_start

    ready_state_case = case(
        (Test.state.in_(("COMPLETED", "NOT REPORTABLE")), 1),
        else_=0,
    )
    ready_tests_subq = (
        select(
            Test.sample_id.label("sample_id"),
            func.count(Test.id).label("total_tests"),
            func.sum(ready_state_case).label("ready_tests"),
        )
        .where(*_test_visibility_conditions())
        .group_by(Test.sample_id)
        .having(func.sum(ready_state_case) == func.count(Test.id))
        .subquery()
    )

    sample_conditions = [
        Sample.date_created.isnot(None),
        Sample.date_created >= window_start,
        Sample.date_created <= reference_dt,
        or_(Order.state.is_(None), Order.state.notin_(("COMPLETED", "REPORTED"))),
    ]
    sample_conditions.extend(_sample_visibility_conditions())

    ready_samples_stmt = (
        select(
            Sample.id.label("sample_id"),
            Sample.sample_name,
            Sample.custom_formatted_id.label("sample_custom_id"),
            Sample.order_id,
            Order.custom_formatted_id.label("order_custom_id"),
            Order.customer_account_id.label("customer_id"),
            Customer.name.label("customer_name"),
            Sample.date_created,
            Sample.completed_date,
            ready_tests_subq.c.ready_tests,
            ready_tests_subq.c.total_tests,
        )
        .select_from(Sample)
        .join(Order, Order.id == Sample.order_id)
        .join(Customer, Customer.id == Order.customer_account_id, isouter=True)
        .join(ready_tests_subq, ready_tests_subq.c.sample_id == Sample.id)
        .where(*sample_conditions)
        .order_by(Sample.date_created.asc())
    )

    ready_samples = [
        ReadyToReportSampleItem(
            sample_id=row.sample_id,
            sample_name=row.sample_name,
            sample_custom_id=row.sample_custom_id,
            order_id=row.order_id,
            order_custom_id=row.order_custom_id,
            customer_id=row.customer_id,
            customer_name=row.customer_name,
            date_created=row.date_created,
            completed_date=row.completed_date,
            tests_ready_count=int(row.ready_tests or 0),
            tests_total_count=int(row.total_tests or 0),
        )
        for row in session.execute(ready_samples_stmt)
    ]

    # Updated Logic: Direct Join with simple filtering for METRC samples
    # 1. Join glims_samples and metrc_sample_statuses on metrc_id
    # 2. Filter by status_window_start (last 30 days)
    metrc_stmt = (
        select(
            Sample.id.label("sample_id"),
            Sample.custom_formatted_id.label("sample_custom_id"),
            Sample.date_created,
            Sample.metrc_id,
            MetrcSampleStatus.metrc_status,
            MetrcSampleStatus.metrc_date,
            Customer.name.label("customer_name"),
        )
        .select_from(Sample)
        .join(Order, Order.id == Sample.order_id)
        .join(Customer, Customer.id == Order.customer_account_id, isouter=True)
        .join(MetrcSampleStatus, MetrcSampleStatus.metrc_id == Sample.metrc_id)
        .where(
            Sample.metrc_id.isnot(None),
            MetrcSampleStatus.metrc_date >= status_window_start,
            MetrcSampleStatus.metrc_date <= reference_dt,
        )
        .where(*_sample_visibility_conditions())
        .order_by(MetrcSampleStatus.metrc_date.desc())
    )

    metrc_samples = []
    # Helper to format days only
    def _format_days_only(dt: datetime) -> str:
        if not dt:
            return "--"
        now_dt = datetime.utcnow() # Use UTC consistent with DB
        delta = now_dt - dt
        days = delta.days
        # If open time is negative (future date), clamp to 0
        return f"{max(0, days)}d"

    for row in session.execute(metrc_stmt):
        open_time = _format_days_only(row.metrc_date)
        metrc_samples.append(
            MetrcSampleStatusItem(
                sample_id=row.sample_id,
                sample_custom_id=row.sample_custom_id,
                date_created=row.date_created,
                metrc_id=row.metrc_id,
                metrc_status=row.metrc_status,
                metrc_date=row.metrc_date,
                open_time_label=open_time,
                customer_name=row.customer_name,
            )
        )

    return OverdueOrdersResponse(
        interval=interval_value,
        minimum_days_overdue=minimum_days,
        warning_window_days=warning_days,
        sla_hours=sla_hours_value,
        kpis=kpis,
        top_orders=top_orders,
        clients=clients,
        warning_orders=warning_orders,
        timeline=timeline,
        heatmap=heatmap,
        state_breakdown=breakdown,
        ready_to_report_samples=ready_samples,
        metrc_samples=metrc_samples,
    )


def get_priority_slowest_reported_orders(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_query: Optional[str] = None,
    min_open_hours: float = 0.0,
    highlight_threshold_hours: Optional[float] = None,
    lookback_days: Optional[int] = None,
    limit: int = 25,
) -> SlowReportedOrdersResponse:
    """Return reported orders with the longest open time within the requested window."""

    effective_limit = max(1, min(limit, 200))
    end_dt = date_to or datetime.now(timezone.utc)
    lookback = 30 if lookback_days is None else max(1, lookback_days)
    start_dt = date_from or (end_dt - timedelta(days=lookback))
    min_open = max(0.0, float(min_open_hours))
    threshold = (
        max(0.0, float(highlight_threshold_hours))
        if highlight_threshold_hours is not None
        else 120.0
    )

    open_hours_expr = _epoch_hours(Order.date_order_reported - Order.date_created)
    conditions = _daterange_conditions(Order.date_order_reported, start_dt, end_dt)
    conditions.extend([Order.date_order_reported.isnot(None), Order.date_created.isnot(None)])
    if min_open > 0:
        conditions.append(open_hours_expr >= min_open)

    if customer_query:
        query_value = customer_query.strip()
        if query_value:
            filters = []
            try:
                filters.append(Order.customer_account_id == int(query_value))
            except ValueError:
                pass
            filters.append(Customer.name.ilike(f"%{query_value}%"))
            conditions.append(or_(*filters))

    stats_stmt = (
        select(
            func.count().label("total"),
            func.avg(open_hours_expr).label("avg"),
            func.percentile_cont(0.95).within_group(open_hours_expr).label("p95"),
        )
        .select_from(Order)
        .join(Customer, Customer.id == Order.customer_account_id, isouter=True)
        .where(*conditions)
    )
    stats_row = session.execute(stats_stmt).one()
    total_orders = int(stats_row.total or 0)
    avg_hours = float(stats_row.avg) if stats_row.avg is not None else None
    p95_hours = float(stats_row.p95) if stats_row.p95 is not None else None

    stmt = (
        select(
            Order.id.label("order_id"),
            func.coalesce(Order.custom_formatted_id, func.concat("ORD-", Order.id)).label("order_reference"),
            Customer.name.label("customer_name"),
            Order.date_created.label("date_created"),
            Order.date_order_reported.label("date_reported"),
            func.coalesce(Order.sample_count, literal(0)).label("samples_count"),
            func.coalesce(Order.test_count, literal(0)).label("tests_count"),
            open_hours_expr.label("open_hours"),
        )
        .select_from(Order)
        .join(Customer, Customer.id == Order.customer_account_id, isouter=True)
        .where(*conditions)
        .order_by(open_hours_expr.desc(), Order.date_order_reported.desc())
        .limit(effective_limit)
    )

    rows = session.execute(stmt)
    items: list[SlowReportedOrderItem] = []
    for row in rows:
        if is_banned(session, "order", int(row.order_id)) or (
            row.customer_name and hasattr(row, "customer_id") and is_banned(session, "customer", int(row.customer_id))
        ):
            continue
        open_hours_value = float(row.open_hours) if row.open_hours is not None else 0.0
        label = _format_open_time_label(open_hours_value)
        is_outlier = threshold is not None and open_hours_value >= threshold
        items.append(
            SlowReportedOrderItem(
                order_id=row.order_id,
                order_reference=row.order_reference,
                customer_name=row.customer_name,
                date_created=row.date_created,
                date_reported=row.date_reported,
                samples_count=int(row.samples_count or 0),
                tests_count=int(row.tests_count or 0),
                open_time_hours=open_hours_value,
                open_time_label=label,
                is_outlier=is_outlier,
            )
        )

    stats = SlowReportedOrdersStats(
        total_orders=total_orders,
        average_open_hours=avg_hours,
        percentile_95_open_hours=p95_hours,
        threshold_hours=threshold,
    )
    return SlowReportedOrdersResponse(stats=stats, items=items)


def get_customer_alerts(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    interval: Optional[str] = "week",
    sla_hours: float = 48.0,
    min_alert_percentage: float = 0.1,
) -> CustomerAlertsResponse:
    """Return heatmap data and alert list for customer quality health."""

    interval_value = _normalise_interval(interval)
    min_alert = max(0.0, min(float(min_alert_percentage), 1.0))
    sla_hours_value = max(0.0, float(sla_hours))

    test_conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=None,
        state=None,
        batch_id=None,
        date_column=Test.date_created,
    )
    test_conditions.append(Test.date_created.isnot(None))

    period_expr = func.date_trunc(interval_value, Test.date_created).label("period")
    on_hold_case = case((Test.state == "ON HOLD", 1), else_=0)
    not_reportable_case = case((Test.state == "NOT REPORTABLE", 1), else_=0)
    tat_expr = func.extract("epoch", func.coalesce(Test.report_completed_date, func.now()) - Test.date_created) / 3600.0
    sla_breach_case = case((tat_expr > sla_hours_value, 1), else_=0)

    heatmap_stmt = (
        select(
            Customer.id.label("customer_id"),
            Customer.name.label("customer_name"),
            period_expr,
            func.count(Test.id).label("total_tests"),
            func.sum(on_hold_case).label("on_hold_tests"),
            func.sum(not_reportable_case).label("not_reportable_tests"),
            func.sum(sla_breach_case).label("sla_breach_tests"),
            func.max(Test.date_created).label("latest_test_at"),
        )
        .select_from(Test)
        .where(*test_conditions)
        .group_by(Customer.id, Customer.name, period_expr)
        .order_by(Customer.name, period_expr)
    )

    heatmap_stmt = heatmap_stmt.join(Sample, Sample.id == Test.sample_id)
    heatmap_stmt = heatmap_stmt.join(Order, Order.id == Sample.order_id)
    heatmap_stmt = heatmap_stmt.join(Customer, Customer.id == Order.customer_account_id)

    heatmap_points: list[CustomerHeatmapPoint] = []
    aggregate_map: dict[int, dict[str, float]] = {}

    for row in session.execute(heatmap_stmt):
        total_tests = int(row.total_tests or 0)
        on_hold_tests = int(row.on_hold_tests or 0)
        not_reportable_tests = int(row.not_reportable_tests or 0)
        sla_breach_tests = int(row.sla_breach_tests or 0)
        period = _convert_period(row.period)

        if total_tests <= 0:
            on_hold_ratio = 0.0
            not_reportable_ratio = 0.0
            sla_breach_ratio = 0.0
        else:
            total_f = float(total_tests)
            on_hold_ratio = on_hold_tests / total_f
            not_reportable_ratio = not_reportable_tests / total_f
            sla_breach_ratio = sla_breach_tests / total_f

        heatmap_points.append(
            CustomerHeatmapPoint(
                customer_id=row.customer_id,
                customer_name=row.customer_name,
                period_start=period,
                total_tests=total_tests,
                on_hold_tests=on_hold_tests,
                not_reportable_tests=not_reportable_tests,
                sla_breach_tests=sla_breach_tests,
                on_hold_ratio=on_hold_ratio,
                not_reportable_ratio=not_reportable_ratio,
                sla_breach_ratio=sla_breach_ratio,
            )
        )

        agg = aggregate_map.setdefault(
            row.customer_id,
            {
                "customer_name": row.customer_name,
                "tests_total": 0,
                "tests_on_hold": 0,
                "tests_not_reportable": 0,
                "tests_beyond_sla": 0,
                "latest_test_at": None,
            },
        )
        agg["tests_total"] += total_tests
        agg["tests_on_hold"] += on_hold_tests
        agg["tests_not_reportable"] += not_reportable_tests
        agg["tests_beyond_sla"] += sla_breach_tests
        latest = row.latest_test_at
        if latest is not None:
            stored = agg.get("latest_test_at")
            if stored is None or latest > stored:
                agg["latest_test_at"] = latest

    order_conditions = _daterange_conditions(Order.date_created, date_from, date_to)
    order_conditions.append(Order.date_created.isnot(None))
    if customer_id is not None:
        order_conditions.append(Order.customer_account_id == customer_id)
    order_conditions.extend(_order_visibility_conditions())

    order_tat_expr = func.extract("epoch", func.coalesce(Order.date_completed, func.now()) - Order.date_created) / 3600.0
    orders_stmt = (
        select(
            Customer.id.label("customer_id"),
            Customer.name.label("customer_name"),
            func.count(Order.id).label("total_orders"),
            func.sum(case((Order.state == "ON HOLD", 1), else_=0)).label("orders_on_hold"),
            func.sum(case((order_tat_expr > sla_hours_value, 1), else_=0)).label("orders_beyond_sla"),
            func.max(Order.date_created).label("latest_order_at"),
        )
        .select_from(Order)
        .join(Customer, Customer.id == Order.customer_account_id)
        .where(*order_conditions)
        .group_by(Customer.id, Customer.name)
    )

    orders_map: dict[int, dict[str, float]] = {}
    for row in session.execute(orders_stmt):
        orders_map[row.customer_id] = {
            "customer_name": row.customer_name,
            "orders_total": int(row.total_orders or 0),
            "orders_on_hold": int(row.orders_on_hold or 0),
            "orders_beyond_sla": int(row.orders_beyond_sla or 0),
            "latest_order_at": row.latest_order_at,
        }

    alerts: list[CustomerAlertItem] = []

    customer_ids = set(aggregate_map.keys()) | set(orders_map.keys())
    for cid in sorted(customer_ids):
        tests_info = aggregate_map.get(
            cid,
            {
                "customer_name": None,
                "tests_total": 0,
                "tests_on_hold": 0,
                "tests_not_reportable": 0,
                "tests_beyond_sla": 0,
                "latest_test_at": None,
            },
        )
        orders_info = orders_map.get(
            cid,
            {
                "customer_name": tests_info.get("customer_name"),
                "orders_total": 0,
                "orders_on_hold": 0,
                "orders_beyond_sla": 0,
                "latest_order_at": None,
            },
        )

        customer_name = tests_info.get("customer_name") or orders_info.get("customer_name")

        tests_total = int(tests_info.get("tests_total", 0))
        tests_on_hold = int(tests_info.get("tests_on_hold", 0))
        tests_not_reportable = int(tests_info.get("tests_not_reportable", 0))
        tests_beyond_sla = int(tests_info.get("tests_beyond_sla", 0))

        orders_total = int(orders_info.get("orders_total", 0))
        orders_on_hold = int(orders_info.get("orders_on_hold", 0))
        orders_beyond_sla = int(orders_info.get("orders_beyond_sla", 0))

        def _ratio(value: int, total: int) -> float:
            return float(value) / float(total) if total > 0 else 0.0

        ratio_map = {
            "tests_on_hold": _ratio(tests_on_hold, tests_total),
            "tests_not_reportable": _ratio(tests_not_reportable, tests_total),
            "tests_beyond_sla": _ratio(tests_beyond_sla, tests_total),
            "orders_on_hold": _ratio(orders_on_hold, orders_total),
            "orders_beyond_sla": _ratio(orders_beyond_sla, orders_total),
        }
        primary_reason, primary_ratio = max(ratio_map.items(), key=lambda item: item[1])

        if primary_ratio < min_alert:
            continue

        latest_activity = tests_info.get("latest_test_at")
        order_latest = orders_info.get("latest_order_at")
        if order_latest and (latest_activity is None or order_latest > latest_activity):
            latest_activity = order_latest

        alerts.append(
            CustomerAlertItem(
                customer_id=cid,
                customer_name=customer_name,
                orders_total=orders_total,
                orders_on_hold=orders_on_hold,
                orders_beyond_sla=orders_beyond_sla,
                tests_total=tests_total,
                tests_on_hold=tests_on_hold,
                tests_not_reportable=tests_not_reportable,
                tests_beyond_sla=tests_beyond_sla,
                primary_reason=primary_reason,
                primary_ratio=primary_ratio,
                latest_activity_at=latest_activity,
            )
        )

    alerts.sort(key=lambda item: item.primary_ratio, reverse=True)

    return CustomerAlertsResponse(
        interval=interval_value,
        sla_hours=sla_hours_value,
        min_alert_percentage=min_alert,
        heatmap=heatmap_points,
        alerts=alerts,
    )


def get_tests_state_distribution(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    interval: Optional[str] = "week",
) -> TestsStateDistributionResponse:
    """Return stacked counts of tests per state grouped by the requested interval."""

    interval_value = _normalise_interval(interval)
    conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=None,
        batch_id=None,
        date_column=Test.date_created,
    )
    conditions.append(Test.date_created.isnot(None))

    period_expr = func.date_trunc(interval_value, Test.date_created).label("period")

    stmt = (
        select(
            period_expr,
            Test.state.label("state"),
            func.count(Test.id).label("count"),
        )
        .select_from(Test)
        .where(*conditions)
        .group_by(period_expr, Test.state)
        .order_by(period_expr)
    )

    if join_sample:
        stmt = stmt.join(Sample, Sample.id == Test.sample_id)
    if join_order:
        stmt = stmt.join(Order, Order.id == Sample.order_id)

    series_map: dict[datetime.date, dict[str, int]] = {}
    states_set: set[str] = set()

    for row in session.execute(stmt):
        period = _convert_period(row.period)
        state = row.state or "UNKNOWN"
        states_set.add(state)
        series_map.setdefault(period, {})[state] = int(row.count or 0)

    totals_stmt = (
        select(
            Test.state.label("state"),
            func.count(Test.id).label("count"),
        )
        .select_from(Test)
        .where(*conditions)
        .group_by(Test.state)
    )
    if join_sample:
        totals_stmt = totals_stmt.join(Sample, Sample.id == Test.sample_id)
    if join_order:
        totals_stmt = totals_stmt.join(Order, Order.id == Sample.order_id)

    totals_map: dict[str, int] = {}
    for state, count in session.execute(totals_stmt):
        key = state or "UNKNOWN"
        totals_map[key] = int(count or 0)
        states_set.add(key)

    states = sorted(states_set)

    def _make_buckets(counts: dict[str, int]) -> tuple[list[TestStateBucket], int]:
        total = sum(counts.values())
        buckets = []
        total = int(total)
        if total <= 0:
            return [], 0
        for state_name in states:
            value = int(counts.get(state_name, 0))
            ratio = float(value) / float(total) if total else 0.0
            buckets.append(TestStateBucket(state=state_name, count=value, ratio=ratio))
        return buckets, total

    series_points: list[TestStatePoint] = []
    for period in sorted(series_map.keys()):
        counts = series_map[period]
        buckets, total = _make_buckets(counts)
        series_points.append(
            TestStatePoint(
                period_start=period,
                total_tests=total,
                buckets=buckets,
            )
        )

    totals_total = sum(totals_map.values())
    totals_buckets = []
    if totals_total > 0:
        for state_name in states:
            value = int(totals_map.get(state_name, 0))
            ratio = float(value) / float(totals_total) if totals_total else 0.0
            totals_buckets.append(TestStateBucket(state=state_name, count=value, ratio=ratio))

    return TestsStateDistributionResponse(
        interval=interval_value,
        states=states,
        series=series_points,
        totals=totals_buckets,
    )


def get_quality_kpis(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    sla_hours: float = 48.0,
) -> QualityKpisResponse:
    """Return aggregated KPIs for quality and SLA monitoring."""

    sla_hours_value = max(0.0, float(sla_hours))

    test_conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=None,
        batch_id=None,
        date_column=Test.date_created,
    )
    test_conditions.append(Test.date_created.isnot(None))

    tat_expr = func.extract("epoch", func.coalesce(Test.report_completed_date, func.now()) - Test.date_created) / 3600.0
    tests_stmt = (
        select(
            func.count(Test.id).label("total_tests"),
            func.sum(case((Test.state == "ON HOLD", 1), else_=0)).label("on_hold_tests"),
            func.sum(case((Test.state == "NOT REPORTABLE", 1), else_=0)).label("not_reportable_tests"),
            func.sum(
                case((Test.state.in_(("CANCELLED", "CLIENT CANCELLED")), 1), else_=0)
            ).label("cancelled_tests"),
            func.sum(case((Test.state == "REPORTED", 1), else_=0)).label("reported_tests"),
            func.sum(case((tat_expr <= sla_hours_value, 1), else_=0)).label("within_sla_tests"),
            func.sum(case((tat_expr > sla_hours_value, 1), else_=0)).label("beyond_sla_tests"),
        )
        .select_from(Test)
        .where(*test_conditions)
    )
    if join_sample:
        tests_stmt = tests_stmt.join(Sample, Sample.id == Test.sample_id)
    if join_order:
        tests_stmt = tests_stmt.join(Order, Order.id == Sample.order_id)

    tests_row = session.execute(tests_stmt).one()

    def _ratio(value: int, total: int) -> float:
        return float(value) / float(total) if total > 0 else 0.0

    tests_total = int(tests_row.total_tests or 0)
    tests_on_hold = int(tests_row.on_hold_tests or 0)
    tests_not_reportable = int(tests_row.not_reportable_tests or 0)
    tests_cancelled = int(tests_row.cancelled_tests or 0)
    tests_reported = int(tests_row.reported_tests or 0)
    tests_within_sla = int(tests_row.within_sla_tests or 0)
    tests_beyond_sla = int(tests_row.beyond_sla_tests or 0)

    tests_kpi = QualityKpiTests(
        total_tests=tests_total,
        on_hold_tests=tests_on_hold,
        not_reportable_tests=tests_not_reportable,
        cancelled_tests=tests_cancelled,
        reported_tests=tests_reported,
        within_sla_tests=tests_within_sla,
        beyond_sla_tests=tests_beyond_sla,
        on_hold_ratio=_ratio(tests_on_hold, tests_total),
        not_reportable_ratio=_ratio(tests_not_reportable, tests_total),
        beyond_sla_ratio=_ratio(tests_beyond_sla, tests_total),
    )

    order_conditions = _daterange_conditions(Order.date_created, date_from, date_to)
    if customer_id is not None:
        order_conditions.append(Order.customer_account_id == customer_id)
    if order_id is not None:
        order_conditions.append(Order.id == order_id)
    order_conditions.append(Order.date_created.isnot(None))

    order_tat_expr = func.extract("epoch", func.coalesce(Order.date_completed, func.now()) - Order.date_created) / 3600.0
    orders_stmt = (
        select(
            func.count(Order.id).label("total_orders"),
            func.sum(case((Order.state == "ON HOLD", 1), else_=0)).label("on_hold_orders"),
            func.sum(case((Order.date_completed.isnot(None), 1), else_=0)).label("completed_orders"),
            func.sum(case((order_tat_expr <= sla_hours_value, 1), else_=0)).label("within_sla_orders"),
            func.sum(case((order_tat_expr > sla_hours_value, 1), else_=0)).label("beyond_sla_orders"),
        )
        .select_from(Order)
        .where(*order_conditions)
    )

    orders_row = session.execute(orders_stmt).one()

    orders_total = int(orders_row.total_orders or 0)
    orders_on_hold = int(orders_row.on_hold_orders or 0)
    orders_completed = int(orders_row.completed_orders or 0)
    orders_within_sla = int(orders_row.within_sla_orders or 0)
    orders_beyond_sla = int(orders_row.beyond_sla_orders or 0)

    orders_kpi = QualityKpiOrders(
        total_orders=orders_total,
        on_hold_orders=orders_on_hold,
        completed_orders=orders_completed,
        within_sla_orders=orders_within_sla,
        beyond_sla_orders=orders_beyond_sla,
        on_hold_ratio=_ratio(orders_on_hold, orders_total),
        beyond_sla_ratio=_ratio(orders_beyond_sla, orders_total),
    )

    return QualityKpisResponse(
        sla_hours=sla_hours_value,
        tests=tests_kpi,
        orders=orders_kpi,
    )


def _select_primary_alias(aliases: Optional[List[str]], name: Optional[str]) -> Optional[str]:
    if not aliases:
        return None
    for alias in aliases:
        if alias and alias != name:
            return alias
    return aliases[0] if aliases else None


def _score_candidate(term: str, name: Optional[str], aliases: Optional[List[str]]) -> tuple[float, Optional[str]]:
    normalized = term.lower()
    best_score = 0.0
    matched_alias = None

    def _score_text(text: Optional[str]) -> float:
        if not text:
            return 0.0
        lowered = text.lower()
        if lowered == normalized:
            return 1.0
        if lowered.startswith(normalized):
            return 0.9
        if normalized in lowered:
            return 0.75
        return 0.0

    score = _score_text(name)
    if score > best_score:
        best_score = score

    for alias in aliases or []:
        alias_score = _score_text(alias)
        if alias_score > best_score:
            best_score = alias_score
            matched_alias = alias

    if best_score == 0.0:
        best_score = 0.6
    return best_score, matched_alias


def _find_customer_matches(session: Session, search_term: str, *, limit: int = 10) -> list[dict]:
    trimmed = (search_term or "").strip()
    if len(trimmed) < 3:
        raise ValueError("customer_name must contain at least 3 characters")
    pattern = f"%{trimmed.lower()}%"
    stmt = (
        select(Customer.id, Customer.name, Customer.aliases)
        .where(
            func.lower(Customer.name).like(pattern)
            | func.lower(func.cast(Customer.aliases, Text)).like(pattern)
        )
        .limit(limit)
    )
    results: list[dict] = []
    for row in session.execute(stmt):
        aliases = list(row.aliases or [])
        score, alias = _score_candidate(trimmed, row.name, aliases)
        results.append(
            {
                "id": row.id,
                "name": row.name,
                "aliases": aliases,
                "alias_match": alias,
                "match_score": score,
            }
        )
    results.sort(key=lambda item: item["match_score"], reverse=True)
    return results


def _order_conditions(customer_id: int, date_from: Optional[datetime], date_to: Optional[datetime]) -> list:
    conditions = [Order.customer_account_id == customer_id]
    if date_from:
        conditions.append(Order.date_created >= date_from)
    if date_to:
        conditions.append(Order.date_created <= date_to)
    conditions.extend(_order_visibility_conditions())
    return conditions


def _classify_sla(age_hours: float, sla_hours: float) -> str:
    if sla_hours <= 0:
        return "ok"
    if age_hours >= sla_hours:
        return "overdue"
    warning_threshold = sla_hours * _WARNING_RATIO
    if age_hours >= warning_threshold:
        return "warning"
    return "ok"


def get_customer_orders_summary(
    session: Session,
    *,
    customer_id: Optional[int] = None,
    customer_name: Optional[str] = None,
    match_strategy: str = "best",
    match_threshold: float = 0.6,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    sla_hours: float = 48.0,
    include_samples: bool = False,
    include_tests: bool = False,
    limit_orders: int = 20,
) -> "CustomerOrdersSummaryResponse":
    from ..schemas.analytics import (
        CustomerMatchedInfo,
        CustomerOrderItem,
        CustomerOrderMetrics,
        CustomerOrdersSummaryResponse,
        CustomerOrdersTopPending,
        CustomerSummaryInfo,
        CustomerTopPendingMatrix,
        CustomerTopPendingTest,
        CustomerLookupMatch,
    )

    if customer_id is None and not customer_name:
        raise ValueError("customer_id or customer_name must be provided")
    strategy = _normalise_match_strategy(match_strategy)
    matched_customer_payload = None

    if customer_id is not None:
        customer = session.get(Customer, customer_id)
        if not customer:
            raise LookupError("customer_not_found")
        matched_customer_payload = CustomerMatchedInfo(
            id=customer.id,
            name=customer.name,
            aliases=list(customer.aliases or []),
            match_score=1.0,
        )
    else:
        matches = _find_customer_matches(session, customer_name or "")
        if not matches:
            raise LookupError("customer_not_found")
        match_models = [
            CustomerLookupMatch(
                id=item["id"],
                name=item["name"],
                alias=item["alias_match"],
                match_score=round(float(item["match_score"]), 4),
            )
            for item in matches
        ]
        if strategy == "all":
            return CustomerOrdersSummaryResponse(matches=match_models)
        best = match_models[0]
        if best.match_score < match_threshold:
            raise LookupError("customer_not_found")
        customer = session.get(Customer, best.id)
        if not customer:
            raise LookupError("customer_not_found")
        matched_customer_payload = CustomerMatchedInfo(
            id=customer.id,
            name=customer.name,
            aliases=list(customer.aliases or []),
            match_score=best.match_score,
        )

    conditions = _order_conditions(customer.id, date_from, date_to)
    total_orders = session.execute(select(func.count()).where(*conditions)).scalar_one()
    last_order_at = session.execute(
        select(func.max(Order.date_created)).where(Order.customer_account_id == customer.id)
    ).scalar_one()

    open_stmt = (
        select(Order.id, Order.state, Order.date_created)
        .where(Order.date_completed.is_(None), Order.date_created.isnot(None), *conditions)
    )
    open_rows = session.execute(open_stmt).all()
    now = datetime.utcnow()
    open_orders = len(open_rows)
    overdue_count = 0
    warning_count = 0
    total_open_hours = 0.0
    order_age_map: dict[int, float] = {}

    for row in open_rows:
        age_hours = 0.0
        if row.date_created:
            delta = now - row.date_created
            age_hours = max(delta.total_seconds() / 3600.0, 0.0)
        order_age_map[row.id] = age_hours
        total_open_hours += age_hours
        classification = _classify_sla(age_hours, sla_hours)
        if classification == "overdue":
            overdue_count += 1
        elif classification == "warning":
            warning_count += 1

    avg_open_hours = total_open_hours / open_orders if open_orders else None

    sorted_rows = sorted(open_rows, key=lambda row: order_age_map[row.id], reverse=True)
    limited_rows = sorted_rows[:limit_orders]
    limited_ids = [row.id for row in limited_rows]

    per_order_samples: dict[int, int] = {}
    per_order_tests: dict[int, int] = {}

    if include_samples and limited_ids:
        sample_stmt = (
            select(Sample.order_id, func.count().label("pending"))
            .where(Sample.order_id.in_(limited_ids), Sample.completed_date.is_(None))
            .group_by(Sample.order_id)
        )
        per_order_samples = {row.order_id: int(row.pending) for row in session.execute(sample_stmt)}

    if include_tests and limited_ids:
        test_stmt = (
            select(Sample.order_id, func.count().label("pending"))
            .select_from(Sample)
            .join(Test, Test.sample_id == Sample.id)
            .where(Sample.order_id.in_(limited_ids), Test.report_completed_date.is_(None))
            .group_by(Sample.order_id)
        )
        per_order_tests = {row.order_id: int(row.pending) for row in session.execute(test_stmt)}

    orders_payload: list[CustomerOrderItem] = []
    for row in limited_rows:
        age_hours = order_age_map.get(row.id, 0.0)
        age_days = int(age_hours // 24)
        orders_payload.append(
            CustomerOrderItem(
                order_id=row.id,
                state=row.state,
                age_days=max(age_days, 0),
                sla_status=_classify_sla(age_hours, sla_hours),
                date_created=row.date_created,
                pending_samples=per_order_samples.get(row.id) if include_samples else None,
                pending_tests=per_order_tests.get(row.id) if include_tests else None,
            )
        )

    pending_samples_total = None
    pending_tests_total = None
    top_matrices: list[CustomerTopPendingMatrix] = []
    top_tests: list[CustomerTopPendingTest] = []

    if include_samples:
        sample_conditions = [
            Order.customer_account_id == customer.id,
            Sample.order_id == Order.id,
            Sample.completed_date.is_(None),
        ]
        if date_from:
            sample_conditions.append(Order.date_created >= date_from)
        if date_to:
            sample_conditions.append(Order.date_created <= date_to)

        pending_samples_total = (
            session.execute(
                select(func.count())
                .select_from(Sample)
                .join(Order, Order.id == Sample.order_id)
                .where(*sample_conditions)
            ).scalar_one_or_none()
            or 0
        )

        matrix_stmt = (
            select(Sample.matrix_type, func.count().label("pending"))
            .join(Order, Order.id == Sample.order_id)
            .where(*sample_conditions)
            .group_by(Sample.matrix_type)
            .order_by(func.count().desc())
            .limit(5)
        )
        top_matrices = [
            CustomerTopPendingMatrix(matrix_type=row.matrix_type, pending_samples=int(row.pending))
            for row in session.execute(matrix_stmt)
        ]

    if include_tests:
        test_conditions = [
            Order.customer_account_id == customer.id,
            Sample.order_id == Order.id,
            Test.sample_id == Sample.id,
            Test.report_completed_date.is_(None),
        ]
        if date_from:
            test_conditions.append(Order.date_created >= date_from)
        if date_to:
            test_conditions.append(Order.date_created <= date_to)

        pending_tests_total = (
            session.execute(
                select(func.count())
                .select_from(Test)
                .join(Sample, Sample.id == Test.sample_id)
                .join(Order, Order.id == Sample.order_id)
                .where(*test_conditions)
            ).scalar_one_or_none()
            or 0
        )

        tests_stmt = (
            select(Test.label_abbr, func.count().label("pending"))
            .join(Sample, Sample.id == Test.sample_id)
            .join(Order, Order.id == Sample.order_id)
            .where(*test_conditions)
            .group_by(Test.label_abbr)
            .order_by(func.count().desc())
            .limit(5)
        )
        top_tests = [
            CustomerTopPendingTest(label_abbr=row.label_abbr, pending_tests=int(row.pending))
            for row in session.execute(tests_stmt)
        ]

    metrics = CustomerOrderMetrics(
        total_orders=int(total_orders),
        open_orders=open_orders,
        overdue_orders=overdue_count,
        warning_orders=warning_count,
        avg_open_duration_hours=round(avg_open_hours, 2) if avg_open_hours is not None else None,
        pending_samples=pending_samples_total,
        pending_tests=pending_tests_total,
        last_updated_at=datetime.now(timezone.utc),
    )

    customer_summary = CustomerSummaryInfo(
        id=customer.id,
        name=customer.name,
        primary_alias=_select_primary_alias(customer.aliases, customer.name),
        last_order_at=last_order_at,
        sla_hours=sla_hours,
    )

    top_pending_block = None
    if include_samples or include_tests:
        top_pending_block = CustomerOrdersTopPending(matrices=top_matrices, tests=top_tests)

    response = CustomerOrdersSummaryResponse(
        matched_customer=matched_customer_payload,
        customer=customer_summary,
        metrics=metrics,
        orders=orders_payload,
        top_pending=top_pending_block,
    )
    return response


