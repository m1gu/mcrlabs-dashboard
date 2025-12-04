"""Query helpers for metrics endpoints."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean, median
from typing import DefaultDict, Iterable, Optional, List

from sqlalchemy import case, exists, func, literal, select
from sqlalchemy.orm import Session

from downloader_qbench_data.storage import BannedEntity, Customer, Order, Sample, Test, SyncCheckpoint
from ..schemas.metrics import (
    DailyActivityPoint,
    DailyActivityResponse,
    DailyTATPoint,
    MetricsFiltersResponse,
    MetricsSummaryKPI,
    MetricsSummaryResponse,
    NewCustomerItem,
    NewCustomersResponse,
    ReportsOverviewResponse,
    SamplesDistributionItem,
    SamplesOverviewKPI,
    SamplesOverviewResponse,
    TestsDistributionItem,
    TestsLabelCountItem,
    TestsLabelDistributionResponse,
    TestsOverviewKPI,
    TestsOverviewResponse,
    TestsTATBreakdownItem,
    TestsTATBreakdownResponse,
    TestsTATDailyResponse,
    TestsTATDistributionBucket,
    TestsTATMetrics,
    TestsTATResponse,
    TimeSeriesPoint,
    TopCustomerItem,
    TopCustomersResponse,
    SyncStatusResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _daterange_conditions(column, start: Optional[datetime], end: Optional[datetime]) -> list:
    conditions = []
    if start:
        conditions.append(column >= start)
    if end:
        if isinstance(end, datetime) and end.hour == 0 and end.minute == 0 and end.second == 0 and end.microsecond == 0:
            adjusted_end = end + timedelta(days=1)
            conditions.append(column < adjusted_end)
        else:
            conditions.append(column <= end)
    return conditions


def _entity_banned_clause(entity: str, column) -> any:
    return exists().where(
        (BannedEntity.entity_type == literal(entity)) & (BannedEntity.entity_id == column)
    )


def _order_visibility_conditions() -> list:
    return [
        ~_entity_banned_clause("order", Order.id),
        ~_entity_banned_clause("customer", Order.customer_account_id),
    ]


def _sample_visibility_conditions() -> list:
    customer_subq = (
        select(Order.customer_account_id)
        .where(Order.id == Sample.order_id)
        .correlate(Sample)
        .scalar_subquery()
    )
    return [
        ~_entity_banned_clause("sample", Sample.id),
        ~_entity_banned_clause("order", Sample.order_id),
        ~_entity_banned_clause("customer", customer_subq),
    ]


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
    return [
        ~_entity_banned_clause("test", Test.id),
        ~_entity_banned_clause("sample", Test.sample_id),
        ~_entity_banned_clause("order", sample_order_subq),
        ~_entity_banned_clause("customer", customer_subq),
    ]


def _customer_visibility_conditions():
    return [~_entity_banned_clause("customer", Customer.id)]


def _apply_sample_filters(
    *,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    customer_id: Optional[int],
    order_id: Optional[int],
    state: Optional[str],
):
    conditions = _daterange_conditions(Sample.date_created, date_from, date_to)
    join_order = False
    if customer_id is not None:
        conditions.append(Order.customer_account_id == customer_id)
        join_order = True
    if order_id is not None:
        conditions.append(Sample.order_id == order_id)
    if state:
        conditions.append(Sample.state == state)
    conditions.extend(_sample_visibility_conditions())
    return conditions, join_order


def _apply_test_filters(
    *,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    customer_id: Optional[int],
    order_id: Optional[int],
    state: Optional[str],
    batch_id: Optional[int],
    date_column=Test.date_created,
):
    conditions: list = []
    if date_column is not None:
        conditions.extend(_daterange_conditions(date_column, date_from, date_to))
    join_sample = False
    join_order = False
    if customer_id is not None:
        join_sample = True
        join_order = True
        conditions.append(Order.customer_account_id == customer_id)
    if order_id is not None:
        join_sample = True
        conditions.append(Sample.order_id == order_id)
    if state:
        conditions.append(Test.state == state)
    if batch_id is not None:
        conditions.append(Test.batch_ids.contains([batch_id]))
    conditions.extend(_test_visibility_conditions())
    return conditions, join_sample, join_order


def _count_with_filters(
    session: Session,
    model,
    *,
    conditions: list,
    join_order: bool = False,
    join_sample: bool = False,
):
    stmt = select(func.count()).select_from(model)
    if model is Sample and join_order:
        stmt = stmt.join(Order, Sample.order_id == Order.id)
    elif model is Test:
        if join_sample:
            stmt = stmt.join(Sample, Sample.id == Test.sample_id)
        if join_order:
            stmt = stmt.join(Order, Sample.order_id == Order.id)
    stmt = stmt.where(*conditions)
    if model is Order:
        stmt = stmt.where(*_order_visibility_conditions())
    return session.execute(stmt).scalar_one()


def _aggregate_counts(
    session: Session,
    column,
    model,
    *,
    conditions: list,
    join_order: bool = False,
    join_sample: bool = False,
):
    stmt = select(column, func.count()).select_from(model)
    if model is Sample and join_order:
        stmt = stmt.join(Order, Sample.order_id == Order.id)
    elif model is Test:
        if join_sample:
            stmt = stmt.join(Sample, Sample.id == Test.sample_id)
        if join_order:
            stmt = stmt.join(Order, Sample.order_id == Order.id)
    stmt = stmt.where(*conditions)
    if model is Order:
        stmt = stmt.where(*_order_visibility_conditions())
    stmt = stmt.group_by(column).order_by(func.count().desc())
    return [(value or "unknown", count) for value, count in session.execute(stmt)]


# ---------------------------------------------------------------------------
# Samples overview
# ---------------------------------------------------------------------------


def get_samples_overview(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    state: Optional[str] = None,
) -> SamplesOverviewResponse:
    conditions, join_order = _apply_sample_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
    )

    total_samples = _count_with_filters(
        session,
        Sample,
        conditions=conditions,
        join_order=join_order,
    )

    completed_conditions = list(conditions) + [Sample.completed_date.is_not(None)]
    completed_samples = _count_with_filters(
        session,
        Sample,
        conditions=completed_conditions,
        join_order=join_order,
    )

    pending_samples = total_samples - completed_samples

    by_state = [
        SamplesDistributionItem(key=value, count=count)
        for value, count in _aggregate_counts(
            session,
            Sample.state,
            Sample,
            conditions=conditions,
            join_order=join_order,
        )
    ]

    by_matrix_type = [
        SamplesDistributionItem(key=value, count=count)
        for value, count in _aggregate_counts(
            session,
            Sample.matrix_type,
            Sample,
            conditions=conditions,
            join_order=join_order,
        )
    ]

    created_vs_completed = [
        SamplesDistributionItem(key="created", count=total_samples),
        SamplesDistributionItem(key="completed", count=completed_samples),
    ]

    return SamplesOverviewResponse(
        kpis=SamplesOverviewKPI(
            total_samples=total_samples,
            completed_samples=completed_samples,
            pending_samples=pending_samples,
        ),
        by_state=by_state,
        by_matrix_type=by_matrix_type,
        created_vs_completed=created_vs_completed,
    )


# ---------------------------------------------------------------------------
# Tests overview
# ---------------------------------------------------------------------------


def get_tests_overview(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    state: Optional[str] = None,
    batch_id: Optional[int] = None,
) -> TestsOverviewResponse:
    conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        batch_id=batch_id,
    )

    total_tests = _count_with_filters(
        session,
        Test,
        conditions=conditions,
        join_sample=join_sample,
        join_order=join_order,
    )

    completed_conditions = list(conditions) + [Test.report_completed_date.is_not(None)]
    completed_tests = _count_with_filters(
        session,
        Test,
        conditions=completed_conditions,
        join_sample=join_sample,
        join_order=join_order,
    )
    pending_tests = total_tests - completed_tests

    by_state = [
        TestsDistributionItem(key=value, count=count)
        for value, count in _aggregate_counts(
            session,
            Test.state,
            Test,
            conditions=conditions,
            join_sample=join_sample,
            join_order=join_order,
        )
    ]

    by_label = [
        TestsDistributionItem(key=value, count=count)
        for value, count in _aggregate_counts(
            session,
            Test.label_abbr,
            Test,
            conditions=conditions,
            join_sample=join_sample,
            join_order=join_order,
        )
    ]

    return TestsOverviewResponse(
        kpis=TestsOverviewKPI(
            total_tests=total_tests,
            completed_tests=completed_tests,
            pending_tests=pending_tests,
        ),
        by_state=by_state,
        by_label=by_label,
    )


# ---------------------------------------------------------------------------
# Tests TAT
# ---------------------------------------------------------------------------


def get_tests_tat(
    session: Session,
    *,
    date_created_from: Optional[datetime] = None,
    date_created_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    state: Optional[str] = None,
    group_by: Optional[str] = None,
    sample_types: Optional[list[str]] = None,
) -> TestsTATResponse:
    conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_created_from,
        date_to=date_created_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        batch_id=None,
        date_column=Test.report_completed_date,
    )
    conditions.append(Test.report_completed_date.is_not(None))
    if sample_types:
        join_sample = True
        conditions.append(Sample.sample_type.in_(sample_types))

    stmt = select(Test.date_created, Test.report_completed_date).select_from(Test)
    if join_sample:
        stmt = stmt.join(Sample, Sample.id == Test.sample_id)
    if join_order:
        stmt = stmt.join(Order, Sample.order_id == Order.id)
    stmt = stmt.where(*conditions)

    tat_values: list[float] = []
    series_acc: DefaultDict[date, list[float]] = defaultdict(list)
    for created_at, completed_at in session.execute(stmt):
        if not created_at or not completed_at:
            continue
        tat_hours = (completed_at - created_at).total_seconds() / 3600.0
        tat_values.append(tat_hours)

        if group_by == "day":
            period = completed_at.date()
        elif group_by == "week":
            iso_year, iso_week, _ = completed_at.isocalendar()
            period = date.fromisocalendar(iso_year, iso_week, 1)
        else:
            period = None
        if period:
            series_acc[period].append(tat_hours)

    metrics = _compute_tat_metrics(tat_values)
    distribution = _make_distribution(tat_values)
    series = [
        TimeSeriesPoint(period_start=period, value=mean(values))
        for period, values in sorted(series_acc.items(), key=lambda item: item[0])
    ]

    return TestsTATResponse(
        metrics=metrics,
        distribution=distribution,
        series=series,
    )


def _compute_tat_metrics(values: Iterable[float]) -> TestsTATMetrics:
    values = [value for value in values if value is not None]
    if not values:
        return TestsTATMetrics(
            average_hours=None,
            median_hours=None,
            p95_hours=None,
            completed_within_sla=0,
            completed_beyond_sla=0,
        )

    sorted_values = sorted(values)
    avg = mean(sorted_values)
    med = median(sorted_values)
    p95_index = max(0, min(int(len(sorted_values) * 0.95) - 1, len(sorted_values) - 1))
    p95 = sorted_values[p95_index]

    within_sla = sum(1 for value in sorted_values if value <= 48)
    beyond_sla = len(sorted_values) - within_sla

    return TestsTATMetrics(
        average_hours=avg,
        median_hours=med,
        p95_hours=p95,
        completed_within_sla=within_sla,
        completed_beyond_sla=beyond_sla,
    )


def _make_distribution(values: Iterable[float]) -> list[TestsTATDistributionBucket]:
    buckets = [
        ("0-24h", 0, 24),
        ("24-48h", 24, 48),
        ("48-72h", 48, 72),
        ("72-168h", 72, 168),
        (">168h", 168, None),
    ]
    counts = {label: 0 for label, _, _ in buckets}
    for value in values:
        if value is None:
            continue
        for label, min_hours, max_hours in buckets:
            if value >= min_hours and (max_hours is None or value < max_hours):
                counts[label] += 1
                break
    return [
        TestsTATDistributionBucket(label=label, count=counts[label])
        for label, _, _ in buckets
    ]


# ---------------------------------------------------------------------------
# Tests TAT breakdown
# ---------------------------------------------------------------------------


def get_tests_tat_breakdown(
    session: Session,
    *,
    date_created_from: Optional[datetime] = None,
    date_created_to: Optional[datetime] = None,
) -> TestsTATBreakdownResponse:
    conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_created_from,
        date_to=date_created_to,
        customer_id=None,
        order_id=None,
        state=None,
        batch_id=None,
    )
    conditions.append(Test.report_completed_date.is_not(None))

    stmt = select(Test.label_abbr, Test.date_created, Test.report_completed_date).select_from(Test)
    if join_sample:
        stmt = stmt.join(Sample, Sample.id == Test.sample_id)
    if join_order:
        stmt = stmt.join(Order, Sample.order_id == Order.id)
    stmt = stmt.where(*conditions)

    grouped: DefaultDict[str, list[float]] = defaultdict(list)
    for label, created_at, completed_at in session.execute(stmt):
        if not created_at or not completed_at:
            continue
        tat_hours = (completed_at - created_at).total_seconds() / 3600.0
        grouped[label or "unknown"].append(tat_hours)

    breakdown = [
        TestsTATBreakdownItem(
            label=label,
            average_hours=mean(values),
            median_hours=median(values),
            p95_hours=_compute_p95(values),
            total_tests=len(values),
        )
        for label, values in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)
    ]
    return TestsTATBreakdownResponse(breakdown=breakdown)


def get_metrics_summary(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    state: Optional[str] = None,
    sla_hours: float = 48.0,
) -> MetricsSummaryResponse:
    sample_conditions, join_order = _apply_sample_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
    )
    total_samples = _count_with_filters(
        session,
        Sample,
        conditions=sample_conditions,
        join_order=join_order,
    )

    test_conditions, join_sample, join_order_tests = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        batch_id=None,
    )
    total_tests = _count_with_filters(
        session,
        Test,
        conditions=test_conditions,
        join_sample=join_sample,
        join_order=join_order_tests,
    )

    customer_conditions = _daterange_conditions(Customer.date_created, date_from, date_to)
    if customer_id is not None:
        customer_conditions.append(Customer.id == customer_id)
    customer_conditions.extend(_customer_visibility_conditions())
    total_customers = session.execute(
        select(func.count()).select_from(Customer).where(*customer_conditions)
    ).scalar_one()

    report_conditions, report_join_sample, report_join_order = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        batch_id=None,
        date_column=Test.report_completed_date,
    )
    report_conditions.append(Test.report_completed_date.is_not(None))
    total_reports = _count_with_filters(
        session,
        Test,
        conditions=report_conditions,
        join_sample=report_join_sample,
        join_order=report_join_order,
    )

    tat_summary = get_tests_tat(
        session,
        date_created_from=date_from,
        date_created_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        sample_types=["Adult Use", "AU Cliente R&D", "Medical MJ"],
    )
    average_tat = tat_summary.metrics.average_hours

    last_updated_at = session.execute(select(func.max(Test.fetched_at))).scalar_one_or_none()

    return MetricsSummaryResponse(
        kpis=MetricsSummaryKPI(
            total_samples=total_samples,
            total_tests=total_tests,
            total_customers=total_customers,
            total_reports=total_reports,
            average_tat_hours=average_tat,
        ),
        last_updated_at=last_updated_at,
        range_start=date_from,
        range_end=date_to,
    )


def get_daily_activity(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    compare_previous: bool = False,
) -> DailyActivityResponse:
    sample_conditions, join_order = _apply_sample_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=None,
    )
    test_conditions, join_sample, join_order_tests = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=None,
        batch_id=None,
    )
    reported_conditions, join_sample_reported, join_order_reported = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=None,
        batch_id=None,
        date_column=Test.report_completed_date,
    )
    reported_conditions.append(Test.report_completed_date.is_not(None))

    current_sample_counts = _fetch_daily_counts(
        session,
        Sample,
        Sample.date_created,
        sample_conditions,
        join_order=join_order,
    )
    current_test_counts = _fetch_daily_counts(
        session,
        Test,
        Test.date_created,
        test_conditions,
        join_order=join_order_tests,
        join_sample=join_sample,
    )
    current_reported_counts = _fetch_daily_counts(
        session,
        Test,
        Test.report_completed_date,
        reported_conditions,
        join_order=join_order_reported,
        join_sample=join_sample_reported,
    )
    current_points = _combine_daily_counts(current_sample_counts, current_test_counts, current_reported_counts)

    previous_points: Optional[list[DailyActivityPoint]] = None
    if compare_previous and date_from and date_to:
        previous_start, previous_end = _calculate_previous_period(date_from, date_to)
        prev_sample_conditions, prev_join_order = _apply_sample_filters(
            date_from=previous_start,
            date_to=previous_end,
            customer_id=customer_id,
            order_id=order_id,
            state=None,
        )
        prev_test_conditions, prev_join_sample, prev_join_order_tests = _apply_test_filters(
            date_from=previous_start,
            date_to=previous_end,
            customer_id=customer_id,
            order_id=order_id,
            state=None,
            batch_id=None,
        )
        prev_report_conditions, prev_join_sample_reported, prev_join_order_reported = _apply_test_filters(
            date_from=previous_start,
            date_to=previous_end,
            customer_id=customer_id,
            order_id=order_id,
            state=None,
            batch_id=None,
            date_column=Test.report_completed_date,
        )
        prev_report_conditions.append(Test.report_completed_date.is_not(None))
        prev_sample_counts = _fetch_daily_counts(
            session,
            Sample,
            Sample.date_created,
            prev_sample_conditions,
            join_order=prev_join_order,
        )
        prev_test_counts = _fetch_daily_counts(
            session,
            Test,
            Test.date_created,
            prev_test_conditions,
            join_order=prev_join_order_tests,
            join_sample=prev_join_sample,
        )
        prev_report_counts = _fetch_daily_counts(
            session,
            Test,
            Test.report_completed_date,
            prev_report_conditions,
            join_order=prev_join_order_reported,
            join_sample=prev_join_sample_reported,
        )
        previous_points = _combine_daily_counts(prev_sample_counts, prev_test_counts, prev_report_counts)

    return DailyActivityResponse(current=current_points, previous=previous_points)


def get_new_customers(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 10,
) -> NewCustomersResponse:
    conditions = _daterange_conditions(Customer.date_created, date_from, date_to)
    conditions.extend(_customer_visibility_conditions())
    stmt = (
        select(Customer.id, Customer.name, Customer.date_created)
        .where(*conditions)
        .order_by(Customer.date_created.desc())
        .limit(limit)
    )
    customers = [
        NewCustomerItem(id=cid, name=name, created_at=created_at)
        for cid, name, created_at in session.execute(stmt)
        if created_at is not None
    ]
    return NewCustomersResponse(customers=customers)


def get_top_customers_by_tests(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 10,
) -> TopCustomersResponse:
    conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=None,
        order_id=None,
        state=None,
        batch_id=None,
    )
    stmt = (
        select(Customer.id, Customer.name, func.count(Test.id))
        .select_from(Test)
        .join(Sample, Sample.id == Test.sample_id)
        .join(Order, Sample.order_id == Order.id)
        .join(Customer, Customer.id == Order.customer_account_id)
        .where(*conditions)
        .group_by(Customer.id, Customer.name)
        .order_by(func.count(Test.id).desc())
        .limit(limit)
    )
    results = list(session.execute(stmt))
    if not results:
        return TopCustomersResponse(customers=[])

    customer_ids = [cid for cid, _, _ in results]

    reported_conditions, _, _ = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=None,
        order_id=None,
        state=None,
        batch_id=None,
        date_column=Test.report_completed_date,
    )
    reported_conditions.append(Test.report_completed_date.is_not(None))
    reported_stmt = (
        select(Customer.id, func.count(Test.id))
        .select_from(Test)
        .join(Sample, Sample.id == Test.sample_id)
        .join(Order, Sample.order_id == Order.id)
        .join(Customer, Customer.id == Order.customer_account_id)
        .where(Customer.id.in_(customer_ids), *reported_conditions)
        .group_by(Customer.id)
    )
    reported_map = {
        cid: count for cid, count in session.execute(reported_stmt)
    }

    customers = [
        TopCustomerItem(
            id=cid,
            name=name,
            tests=count,
            tests_reported=int(reported_map.get(cid, 0)),
        )
        for cid, name, count in results
    ]
    return TopCustomersResponse(customers=customers)


def get_sync_status(
    session: Session,
    *,
    entity: str,
) -> SyncStatusResponse:
    updated_at = session.execute(
        select(SyncCheckpoint.updated_at).where(SyncCheckpoint.entity == entity)
    ).scalar_one_or_none()
    return SyncStatusResponse(entity=entity, updated_at=updated_at)


def get_reports_overview(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    state: Optional[str] = None,
    sla_hours: float = 48.0,
) -> ReportsOverviewResponse:
    conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state="REPORTED",
        batch_id=None,
        date_column=Test.report_completed_date,
    )
    conditions.append(Test.report_completed_date.is_not(None))

    tat_expr = func.extract("epoch", Test.report_completed_date - Test.date_created) / 3600.0
    within_case = case((tat_expr <= sla_hours, 1), else_=0)
    beyond_case = case((tat_expr > sla_hours, 1), else_=0)

    stmt = select(
        func.count(),
        func.sum(within_case),
        func.sum(beyond_case),
    ).select_from(Test)
    if join_sample:
        stmt = stmt.join(Sample, Sample.id == Test.sample_id)
    if join_order:
        stmt = stmt.join(Order, Sample.order_id == Order.id)
    stmt = stmt.where(*conditions)

    total_reports, within_sla, beyond_sla = session.execute(stmt).one()
    return ReportsOverviewResponse(
        total_reports=int(total_reports or 0),
        reports_within_sla=int(within_sla or 0),
        reports_beyond_sla=int(beyond_sla or 0),
    )


def get_tests_tat_daily(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    state: Optional[str] = None,
    sla_hours: float = 48.0,
    moving_average_window: int = 7,
) -> TestsTATDailyResponse:
    conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        batch_id=None,
        date_column=Test.report_completed_date,
    )
    conditions.append(Test.report_completed_date.is_not(None))

    tat_expr = func.extract("epoch", Test.report_completed_date - Test.date_created) / 3600.0
    within_case = case((tat_expr <= sla_hours, 1), else_=0)
    beyond_case = case((tat_expr > sla_hours, 1), else_=0)
    period = func.date_trunc("day", Test.report_completed_date).label("period")

    stmt = (
        select(
            period,
            func.avg(tat_expr),
            func.sum(within_case),
            func.sum(beyond_case),
        )
        .select_from(Test)
    )
    if join_sample:
        stmt = stmt.join(Sample, Sample.id == Test.sample_id)
    if join_order:
        stmt = stmt.join(Order, Sample.order_id == Order.id)
    stmt = stmt.where(*conditions).group_by(period).order_by(period)

    points: list[DailyTATPoint] = []
    averages: list[TimeSeriesPoint] = []
    for day, avg_hours, within_sla_value, beyond_sla_value in session.execute(stmt):
        point_date = day.date()
        avg_value = float(avg_hours) if avg_hours is not None else None
        points.append(
            DailyTATPoint(
                date=point_date,
                average_hours=avg_value,
                within_sla=int(within_sla_value or 0),
                beyond_sla=int(beyond_sla_value or 0),
            )
        )

    if moving_average_window and moving_average_window > 1 and points:
        averages = _calculate_moving_average(points, moving_average_window)

    return TestsTATDailyResponse(points=points, moving_average_hours=averages or None)


def _fetch_daily_counts(
    session: Session,
    model,
    column,
    conditions: list,
    *,
    join_order: bool = False,
    join_sample: bool = False,
) -> dict[date, int]:
    period = func.date_trunc("day", column)
    stmt = select(period.label("period"), func.count()).select_from(model)
    if model is Sample and join_order:
        stmt = stmt.join(Order, Sample.order_id == Order.id)
    elif model is Test:
        if join_sample:
            stmt = stmt.join(Sample, Sample.id == Test.sample_id)
        if join_order:
            stmt = stmt.join(Order, Sample.order_id == Order.id)
    stmt = stmt.where(*conditions).group_by(period).order_by(period)

    counts: dict[date, int] = {}
    for row in session.execute(stmt):
        if row.period is None:
            continue
        counts[row.period.date()] = int(row[1] or 0)
    return counts


def _combine_daily_counts(
    samples: dict[date, int],
    tests_created: dict[date, int],
    tests_reported: Optional[dict[date, int]] = None,
) -> list[DailyActivityPoint]:
    reported_map = tests_reported or {}
    all_dates = sorted(set(samples.keys()) | set(tests_created.keys()) | set(reported_map.keys()))
    return [
        DailyActivityPoint(
            date=point_date,
            samples=samples.get(point_date, 0),
            tests=tests_created.get(point_date, 0),
            tests_reported=reported_map.get(point_date, 0),
        )
        for point_date in all_dates
    ]


def _calculate_previous_period(date_from: datetime, date_to: datetime) -> tuple[datetime, datetime]:
    span_days = (date_to.date() - date_from.date()).days + 1
    prev_end = date_from - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span_days - 1)
    return prev_start, prev_end


def _calculate_moving_average(points: list[DailyTATPoint], window: int) -> list[TimeSeriesPoint]:
    averages: list[TimeSeriesPoint] = []
    values: list[float] = []
    dates: list[date] = []
    for point in points:
        if point.average_hours is None:
            continue
        values.append(point.average_hours)
        dates.append(point.date)
        if len(values) >= window:
            window_values = values[-window:]
            averages.append(
                TimeSeriesPoint(
                    period_start=dates[-1],
                    value=sum(window_values) / len(window_values),
                )
            )
    return averages


def _compute_p95(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = max(0, min(int(len(sorted_values) * 0.95) - 1, len(sorted_values) - 1))
    return sorted_values[index]


# ---------------------------------------------------------------------------
# Tests label distribution
# ---------------------------------------------------------------------------


def get_tests_label_distribution(
    session: Session,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    state: Optional[str] = None,
) -> TestsLabelDistributionResponse:
    """Return counts for predefined test labels in the given range."""

    target_labels = [
        "CN",
        "MB",
        "TP",
        "MY",
        "HM",
        "FFM",
        "HO",
        "HLVd",
        "MC",
        "PS",
        "PN",
        "RS",
        "ST",
        "SP",
        "WA",
        "YM",
    ]

    conditions, join_sample, join_order = _apply_test_filters(
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        order_id=order_id,
        state=state,
        batch_id=None,
        date_column=Test.date_created,
    )
    conditions.append(Test.label_abbr.in_(target_labels))

    stmt = select(Test.label_abbr, func.count()).select_from(Test)
    if join_sample:
        stmt = stmt.join(Sample, Sample.id == Test.sample_id)
    if join_order:
        stmt = stmt.join(Order, Sample.order_id == Order.id)
    stmt = stmt.where(*conditions).group_by(Test.label_abbr)

    counts = {label: 0 for label in target_labels}
    for label, count in session.execute(stmt):
        if not label:
            continue
        counts[label] = int(count or 0)

    ordered = sorted(
        [TestsLabelCountItem(label=label, count=counts[label]) for label in target_labels],
        key=lambda item: item.count,
        reverse=True,
    )
    return TestsLabelDistributionResponse(labels=ordered)


# ---------------------------------------------------------------------------
# Filters endpoint
# ---------------------------------------------------------------------------


def get_metrics_filters(session: Session) -> MetricsFiltersResponse:
    customers_stmt = (
        select(Customer.id, Customer.name)
        .where(*_customer_visibility_conditions())
        .order_by(Customer.name)
    )
    customers = [
        {"id": cid, "name": name}
        for cid, name in session.execute(customers_stmt)
    ]
    sample_states = sorted(
        {
            state
            for (state,) in session.execute(
                select(func.distinct(Sample.state)).where(*_sample_visibility_conditions())
            )
            if state
        }
    )
    test_states = sorted(
        {
            state
            for (state,) in session.execute(
                select(func.distinct(Test.state)).where(*_test_visibility_conditions())
            )
            if state
        }
    )
    last_updated_at = session.execute(select(func.max(Test.fetched_at))).scalar_one_or_none()
    return MetricsFiltersResponse(
        customers=customers,
        sample_states=sample_states,
        test_states=test_states,
        last_updated_at=last_updated_at,
    )
