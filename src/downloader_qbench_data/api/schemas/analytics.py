"""Pydantic schemas for analytics endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class OrdersThroughputPoint(BaseModel):
    period_start: date = Field(..., description="Beginning of the aggregation interval")
    orders_created: int = Field(..., description="Orders created during the interval")
    orders_completed: int = Field(..., description="Orders completed during the interval")
    average_completion_hours: Optional[float] = Field(
        None, description="Average hours from creation to completion for orders completed in the interval"
    )
    median_completion_hours: Optional[float] = Field(
        None, description="Median hours from creation to completion for orders completed in the interval"
    )


class OrdersThroughputTotals(BaseModel):
    orders_created: int
    orders_completed: int
    average_completion_hours: Optional[float]
    median_completion_hours: Optional[float]


class OrdersThroughputResponse(BaseModel):
    interval: str = Field(..., description="Aggregation granularity: day or week")
    points: list[OrdersThroughputPoint]
    totals: OrdersThroughputTotals


class SamplesCycleTimePoint(BaseModel):
    period_start: date
    completed_samples: int
    average_cycle_hours: Optional[float]
    median_cycle_hours: Optional[float]


class SamplesCycleMatrixItem(BaseModel):
    matrix_type: str
    completed_samples: int
    average_cycle_hours: Optional[float]


class SamplesCycleTimeTotals(BaseModel):
    completed_samples: int
    average_cycle_hours: Optional[float]
    median_cycle_hours: Optional[float]


class SamplesCycleTimeResponse(BaseModel):
    interval: str = Field(..., description="Aggregation granularity: day or week")
    points: list[SamplesCycleTimePoint]
    totals: SamplesCycleTimeTotals
    by_matrix_type: list[SamplesCycleMatrixItem]


class OrdersFunnelStage(BaseModel):
    stage: str
    count: int


class OrdersFunnelResponse(BaseModel):
    total_orders: int = Field(..., description="Orders created within the requested range")
    stages: list[OrdersFunnelStage]


class SlowOrderItem(BaseModel):
    order_id: int = Field(..., description="Internal order identifier")
    order_reference: str = Field(..., description="Display-friendly order code")
    customer_name: Optional[str] = Field(None, description="Customer linked to the order")
    state: Optional[str] = Field(None, description="Current order state")
    completion_hours: Optional[float] = Field(
        None,
        description="Hours from order creation to completion. Null when order is not completed.",
    )
    age_hours: float = Field(..., description="Hours since creation up to completion or reference time")
    date_created: Optional[datetime] = Field(None, description="Order creation timestamp")
    date_completed: Optional[datetime] = Field(None, description="Order completion timestamp")


class OrdersSlowestResponse(BaseModel):
    items: list[SlowOrderItem]


class SlowReportedOrderItem(BaseModel):
    order_id: int = Field(..., description="Internal order identifier")
    order_reference: str = Field(..., description="Display-friendly order code")
    customer_name: Optional[str] = Field(None, description="Customer linked to the order")
    date_created: Optional[datetime] = Field(None, description="Order creation timestamp")
    date_reported: Optional[datetime] = Field(None, description="Order reported timestamp")
    samples_count: int = Field(..., description="Number of samples linked to the order")
    tests_count: int = Field(..., description="Number of tests linked to the order")
    open_time_hours: float = Field(..., description="Hours from creation to report")
    open_time_label: str = Field(..., description="Human-readable open time representation (e.g. '3d 4h')")
    is_outlier: bool = Field(False, description="Whether the order exceeds the configured threshold")


class SlowReportedOrdersStats(BaseModel):
    total_orders: int = Field(..., description="Orders included in the lookback window after filters")
    average_open_hours: Optional[float] = Field(None, description="Average open hours for the filtered set")
    percentile_95_open_hours: Optional[float] = Field(None, description="95th percentile open hours for the filtered set")
    threshold_hours: Optional[float] = Field(None, description="Threshold used to highlight outliers")


class SlowReportedOrdersResponse(BaseModel):
    stats: SlowReportedOrdersStats
    items: list[SlowReportedOrderItem]


class CustomerHeatmapPoint(BaseModel):
    customer_id: int = Field(..., description="Customer identifier")
    customer_name: Optional[str] = Field(None, description="Customer display name")
    period_start: date = Field(..., description="Beginning of the aggregation interval")
    total_tests: int = Field(..., description="Total tests in the interval")
    on_hold_tests: int = Field(..., description="Tests with ON HOLD state")
    not_reportable_tests: int = Field(..., description="Tests with NOT REPORTABLE state")
    sla_breach_tests: int = Field(..., description="Tests beyond SLA threshold")
    on_hold_ratio: float = Field(..., description="Fraction of tests ON HOLD in the interval")
    not_reportable_ratio: float = Field(..., description="Fraction of tests NOT REPORTABLE in the interval")
    sla_breach_ratio: float = Field(..., description="Fraction of tests beyond SLA in the interval")


class CustomerAlertItem(BaseModel):
    customer_id: int
    customer_name: Optional[str] = None
    orders_total: int
    orders_on_hold: int
    orders_beyond_sla: int
    tests_total: int
    tests_on_hold: int
    tests_not_reportable: int
    tests_beyond_sla: int
    primary_reason: str = Field(..., description="Metric with highest breach ratio")
    primary_ratio: float = Field(..., description="Maximum breach ratio used for alert ranking")
    latest_activity_at: Optional[datetime] = Field(None, description="Timestamp of the most recent related activity")


class CustomerAlertsResponse(BaseModel):
    interval: str
    sla_hours: float
    min_alert_percentage: float
    heatmap: list[CustomerHeatmapPoint]
    alerts: list[CustomerAlertItem]


class TestStateBucket(BaseModel):
    state: str
    count: int
    ratio: float = Field(..., description="Fraction of tests for the bucket relative to the point total")


class TestStatePoint(BaseModel):
    period_start: date
    total_tests: int
    buckets: list[TestStateBucket]


class TestsStateDistributionResponse(BaseModel):
    interval: str
    states: list[str]
    series: list[TestStatePoint]
    totals: list[TestStateBucket]


class QualityKpiTests(BaseModel):
    total_tests: int
    on_hold_tests: int
    not_reportable_tests: int
    cancelled_tests: int
    reported_tests: int
    within_sla_tests: int
    beyond_sla_tests: int
    on_hold_ratio: float
    not_reportable_ratio: float
    beyond_sla_ratio: float


class QualityKpiOrders(BaseModel):
    total_orders: int
    on_hold_orders: int
    completed_orders: int
    within_sla_orders: int
    beyond_sla_orders: int
    on_hold_ratio: float
    beyond_sla_ratio: float


class QualityKpisResponse(BaseModel):
    sla_hours: float
    tests: QualityKpiTests
    orders: QualityKpiOrders


class CustomerLookupMatch(BaseModel):
    id: int
    name: str
    alias: Optional[str] = Field(None, description="Alias that matched the lookup term, if any")
    match_score: float = Field(..., ge=0.0, le=1.0)


class CustomerMatchedInfo(BaseModel):
    id: int
    name: str
    aliases: list[str] = Field(default_factory=list)
    match_score: float = Field(..., ge=0.0, le=1.0)


class CustomerSummaryInfo(BaseModel):
    id: int
    name: str
    primary_alias: Optional[str] = None
    last_order_at: Optional[datetime] = None
    sla_hours: float


class CustomerOrderMetrics(BaseModel):
    total_orders: int
    open_orders: int
    overdue_orders: int
    warning_orders: int
    avg_open_duration_hours: Optional[float] = Field(
        None, description="Average hours elapsed for currently open orders"
    )
    pending_samples: Optional[int] = Field(
        None, description="Pending samples for the customer when include_samples=true"
    )
    pending_tests: Optional[int] = Field(
        None, description="Pending tests for the customer when include_tests=true"
    )
    last_updated_at: datetime


class CustomerOrderItem(BaseModel):
    order_id: int
    state: Optional[str] = None
    age_days: int = Field(..., ge=0)
    sla_status: str = Field(..., description="ok, warning or overdue")
    date_created: Optional[datetime] = None
    pending_samples: Optional[int] = None
    pending_tests: Optional[int] = None


class CustomerTopPendingMatrix(BaseModel):
    matrix_type: Optional[str] = None
    pending_samples: int


class CustomerTopPendingTest(BaseModel):
    label_abbr: Optional[str] = None
    pending_tests: int


class CustomerOrdersTopPending(BaseModel):
    matrices: list[CustomerTopPendingMatrix] = Field(default_factory=list)
    tests: list[CustomerTopPendingTest] = Field(default_factory=list)


class CustomerOrdersSummaryResponse(BaseModel):
    matches: Optional[list[CustomerLookupMatch]] = Field(
        None, description="Returned when match_strategy=all to help pick a customer"
    )
    matched_customer: Optional[CustomerMatchedInfo] = None
    customer: Optional[CustomerSummaryInfo] = None
    metrics: Optional[CustomerOrderMetrics] = None
    orders: Optional[list[CustomerOrderItem]] = None
    top_pending: Optional[CustomerOrdersTopPending] = None


class OverdueOrdersKpis(BaseModel):
    total_overdue: int = Field(..., description="Orders older than the minimum overdue window")
    average_open_hours: Optional[float] = Field(None, description="Average open hours for overdue orders")
    max_open_hours: Optional[float] = Field(None, description="Maximum open hours for overdue orders")
    percent_overdue_vs_active: float = Field(..., description="Fraction of active orders that are overdue")
    overdue_beyond_sla: int = Field(..., description="Overdue orders exceeding the SLA threshold")
    overdue_within_sla: int = Field(..., description="Overdue orders still within SLA")


class OverdueTestDetail(BaseModel):
    primary_test_id: int
    test_ids: list[int]
    label_abbr: Optional[str] = None
    states: list[str]


class OverdueSampleDetail(BaseModel):
    sample_id: int
    sample_custom_id: Optional[str] = None
    sample_name: Optional[str] = None
    matrix_type: Optional[str] = None
    total_tests: int
    incomplete_tests: int
    tests: list[OverdueTestDetail]


class OverdueOrderItem(BaseModel):
    order_id: int
    custom_formatted_id: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    state: Optional[str] = None
    date_created: Optional[datetime] = None
    open_hours: float = Field(..., description="Hours since order creation up to the reference time")
    total_samples: int = Field(0, description="Total samples linked to the order")
    incomplete_sample_count: int = Field(0, description="Samples with tests not yet reported")
    incomplete_samples: list[OverdueSampleDetail] = Field(default_factory=list, description="Samples with outstanding tests")


class OverdueClientSummary(BaseModel):
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    overdue_orders: int
    total_open_hours: float
    average_open_hours: Optional[float]
    max_open_hours: Optional[float]


class OverdueTimelinePoint(BaseModel):
    period_start: date
    overdue_orders: int


class OverdueHeatmapCell(BaseModel):
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    period_start: date
    overdue_orders: int


class OverdueStateBreakdown(BaseModel):
    state: Optional[str] = None
    count: int
    ratio: float


class ReadyToReportSampleItem(BaseModel):
    sample_id: int
    sample_name: Optional[str] = None
    sample_custom_id: Optional[str] = None
    order_id: int
    order_custom_id: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    date_created: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    tests_ready_count: int = Field(..., description="Number of tests in ready states for the sample")
    tests_total_count: int = Field(..., description="Total tests associated with the sample")


class MetrcSampleStatusItem(BaseModel):
    sample_id: int
    sample_custom_id: Optional[str] = None
    date_created: Optional[datetime] = None
    metrc_id: str
    metrc_status: Optional[str] = None
    metrc_date: Optional[datetime] = None
    customer_name: Optional[str] = None


class OverdueOrdersResponse(BaseModel):
    interval: str
    minimum_days_overdue: int
    warning_window_days: int
    sla_hours: float
    kpis: OverdueOrdersKpis
    top_orders: list[OverdueOrderItem]
    clients: list[OverdueClientSummary]
    warning_orders: list[OverdueOrderItem]
    timeline: list[OverdueTimelinePoint]
    heatmap: list[OverdueHeatmapCell]
    state_breakdown: list[OverdueStateBreakdown]
    ready_to_report_samples: list[ReadyToReportSampleItem]
    metrc_samples: list[MetrcSampleStatusItem]
