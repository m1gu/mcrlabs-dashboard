"""Pydantic schemas for metrics endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class SamplesOverviewKPI(BaseModel):
    total_samples: int = Field(..., description="Total samples within the filter scope")
    completed_samples: int = Field(..., description="Samples with completed_date within the range")
    pending_samples: int = Field(..., description="Samples lacking completion state within the range")


class SamplesDistributionItem(BaseModel):
    key: str
    count: int


class SamplesOverviewResponse(BaseModel):
    kpis: SamplesOverviewKPI
    by_state: list[SamplesDistributionItem]
    by_matrix_type: list[SamplesDistributionItem]
    created_vs_completed: list[SamplesDistributionItem]


class TestsOverviewKPI(BaseModel):
    total_tests: int
    completed_tests: int
    pending_tests: int


class TestsDistributionItem(BaseModel):
    key: str
    count: int


class TestsOverviewResponse(BaseModel):
    kpis: TestsOverviewKPI
    by_state: list[TestsDistributionItem]
    by_label: list[TestsDistributionItem]


class TimeSeriesPoint(BaseModel):
    period_start: date
    value: float


class TestsTATMetrics(BaseModel):
    average_hours: float | None
    median_hours: float | None
    p95_hours: float | None
    completed_within_sla: int
    completed_beyond_sla: int


class TestsTATDistributionBucket(BaseModel):
    label: str
    count: int


class TestsTATResponse(BaseModel):
    metrics: TestsTATMetrics
    distribution: list[TestsTATDistributionBucket]
    series: list[TimeSeriesPoint]


class TestsTATBreakdownItem(BaseModel):
    label: str
    average_hours: float | None
    median_hours: float | None
    p95_hours: float | None
    total_tests: int


class TestsTATBreakdownResponse(BaseModel):
    breakdown: list[TestsTATBreakdownItem]


class MetricsFiltersResponse(BaseModel):
    customers: list[dict[str, int | str]]
    sample_states: list[str]
    test_states: list[str]
    last_updated_at: Optional[datetime] = None


class MetricsSummaryKPI(BaseModel):
    total_samples: int
    total_tests: int
    total_customers: int
    total_reports: int
    average_tat_hours: Optional[float]


class MetricsSummaryResponse(BaseModel):
    kpis: MetricsSummaryKPI
    last_updated_at: Optional[datetime]
    range_start: Optional[datetime]
    range_end: Optional[datetime]


class DailyActivityPoint(BaseModel):
    date: date
    samples: int
    tests: int
    tests_reported: int


class DailyActivityResponse(BaseModel):
    current: list[DailyActivityPoint]
    previous: Optional[list[DailyActivityPoint]] = None


class NewCustomerItem(BaseModel):
    id: int
    name: str
    created_at: datetime


class NewCustomersResponse(BaseModel):
    customers: list[NewCustomerItem]


class TopCustomerItem(BaseModel):
    id: int
    name: str
    tests: int
    tests_reported: int


class TopCustomersResponse(BaseModel):
    customers: list[TopCustomerItem]


class SyncStatusResponse(BaseModel):
    entity: str
    updated_at: Optional[datetime]


class ReportsOverviewResponse(BaseModel):
    total_reports: int
    reports_within_sla: int
    reports_beyond_sla: int


class DailyTATPoint(BaseModel):
    date: date
    average_hours: Optional[float]
    within_sla: int
    beyond_sla: int


class TestsTATDailyResponse(BaseModel):
    points: list[DailyTATPoint]
    moving_average_hours: Optional[list[TimeSeriesPoint]] = None


class TestsLabelCountItem(BaseModel):
    label: str
    count: int


class TestsLabelDistributionResponse(BaseModel):
    labels: list[TestsLabelCountItem]
