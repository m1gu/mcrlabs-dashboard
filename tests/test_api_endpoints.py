from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from downloader_qbench_data.api import create_app
from downloader_qbench_data.api.dependencies import get_db_session, require_active_user
from downloader_qbench_data.api.schemas import (
    CustomerAlertItem,
    CustomerAlertsResponse,
    CustomerLookupMatch,
    CustomerMatchedInfo,
    CustomerHeatmapPoint,
    CustomerOrderItem,
    CustomerOrderMetrics,
    CustomerOrdersSummaryResponse,
    CustomerOrdersTopPending,
    CustomerSummaryInfo,
    CustomerTopPendingMatrix,
    CustomerTopPendingTest,
    DailyActivityPoint,
    DailyActivityResponse,
    DailyTATPoint,
    MetricsFiltersResponse,
    MetricsSummaryKPI,
    MetricsSummaryResponse,
    NewCustomerItem,
    NewCustomersResponse,
    OrderDetailResponse,
    OrderSampleItem,
    OrderSampleTestItem,
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
    MetrcSampleStatusItem,
    ReadyToReportSampleItem,
    QualityKpiOrders,
    QualityKpiTests,
    QualityKpisResponse,
    ReportsOverviewResponse,
    SampleBatchItem,
    SampleDetailResponse,
    SampleTestItem,
    SamplesCycleMatrixItem,
    SamplesCycleTimePoint,
    SamplesCycleTimeResponse,
    SamplesCycleTimeTotals,
    SamplesDistributionItem,
    SamplesOverviewKPI,
    SamplesOverviewResponse,
    SlowOrderItem,
    SlowReportedOrderItem,
    SlowReportedOrdersResponse,
    SlowReportedOrdersStats,
    SyncStatusResponse,
    TestBatchItem,
    TestDetailResponse,
    TestStateBucket,
    TestStatePoint,
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
    TestsStateDistributionResponse,
    TimeSeriesPoint,
    TopCustomerItem,
    TopCustomersResponse,
)


def create_test_client(monkeypatch):
    app = create_app()
    def _dummy_session():
        yield object()
    app.dependency_overrides[get_db_session] = _dummy_session
    app.dependency_overrides[require_active_user] = lambda: SimpleNamespace(username="tester")
    client = TestClient(app)
    return client


def test_metrics_summary_endpoint(monkeypatch):
    response_payload = MetricsSummaryResponse(
        kpis=MetricsSummaryKPI(
            total_samples=205,
            total_tests=616,
            total_customers=4,
            total_reports=74,
            average_tat_hours=42.0,
        ),
        last_updated_at=None,
        range_start=datetime(2025, 10, 11),
        range_end=datetime(2025, 10, 17),
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_metrics_summary",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/summary")
    assert resp.status_code == 200
    assert resp.json()["kpis"]["total_tests"] == 616


def test_daily_activity_endpoint(monkeypatch):
    response_payload = DailyActivityResponse(
        current=[
            DailyActivityPoint(date=date(2025, 10, 15), samples=20, tests=40, tests_reported=22),
            DailyActivityPoint(date=date(2025, 10, 16), samples=25, tests=50, tests_reported=28),
        ],
        previous=[
            DailyActivityPoint(date=date(2025, 10, 13), samples=10, tests=20, tests_reported=12),
            DailyActivityPoint(date=date(2025, 10, 14), samples=15, tests=30, tests_reported=18),
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_daily_activity",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/activity/daily?compare_previous=true")
    assert resp.status_code == 200
    assert len(resp.json()["current"]) == 2


def test_new_customers_endpoint(monkeypatch):
    response_payload = NewCustomersResponse(
        customers=[
            NewCustomerItem(id=1, name="Acme", created_at=datetime(2025, 10, 16)),
            NewCustomerItem(id=2, name="Globex", created_at=datetime(2025, 10, 15)),
        ]
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_new_customers",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/customers/new")
    assert resp.status_code == 200
    assert resp.json()["customers"][0]["name"] == "Acme"


def test_top_customers_endpoint(monkeypatch):
    response_payload = TopCustomersResponse(
        customers=[
            TopCustomerItem(id=1, name="Acme", tests=50, tests_reported=32),
            TopCustomerItem(id=2, name="Globex", tests=30, tests_reported=18),
        ]
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_top_customers_by_tests",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/customers/top-tests")
    assert resp.status_code == 200
    assert resp.json()["customers"][0]["tests"] == 50
    assert resp.json()["customers"][0]["tests_reported"] == 32


def test_sync_status_endpoint(monkeypatch):
    response_payload = SyncStatusResponse(
        entity="tests",
        updated_at=datetime(2025, 10, 30, 11, 47, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_sync_status",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/sync/status?entity=tests")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity"] == "tests"
    assert body["updated_at"] == "2025-10-30T11:47:00+00:00"


def test_reports_overview_endpoint(monkeypatch):
    response_payload = ReportsOverviewResponse(
        total_reports=74,
        reports_within_sla=60,
        reports_beyond_sla=14,
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_reports_overview",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/reports/overview")
    assert resp.status_code == 200
    assert resp.json()["reports_within_sla"] == 60


def test_tests_tat_daily_endpoint(monkeypatch):
    response_payload = TestsTATDailyResponse(
        points=[
            DailyTATPoint(date=date(2025, 10, 15), average_hours=40, within_sla=30, beyond_sla=5),
            DailyTATPoint(date=date(2025, 10, 16), average_hours=42, within_sla=28, beyond_sla=6),
        ],
        moving_average_hours=[
            TimeSeriesPoint(period_start=date(2025, 10, 16), value=41.0),
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_tests_tat_daily",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/tests/tat-daily")
    assert resp.status_code == 200
    assert resp.json()["points"][0]["within_sla"] == 30


def test_customer_orders_summary_endpoint(monkeypatch):
    response_payload = CustomerOrdersSummaryResponse(
        matched_customer=CustomerMatchedInfo(id=742, name="La Casa de las Flores", aliases=["Casa Flores"], match_score=0.94),
        customer=CustomerSummaryInfo(
            id=742,
            name="La Casa de las Flores",
            primary_alias="Casa Flores",
            last_order_at=datetime(2025, 11, 6, 18, 40, tzinfo=timezone.utc),
            sla_hours=36,
        ),
        metrics=CustomerOrderMetrics(
            total_orders=12,
            open_orders=4,
            overdue_orders=1,
            warning_orders=1,
            avg_open_duration_hours=28.5,
            pending_samples=9,
            pending_tests=34,
            last_updated_at=datetime(2025, 11, 9, 12, 0, tzinfo=timezone.utc),
        ),
        orders=[
            CustomerOrderItem(
                order_id=90124,
                state="in_progress",
                age_days=3,
                sla_status="warning",
                date_created=datetime(2025, 11, 6, 9, 12, tzinfo=timezone.utc),
                pending_samples=2,
                pending_tests=7,
            )
        ],
        top_pending=CustomerOrdersTopPending(
            matrices=[CustomerTopPendingMatrix(matrix_type="Blood", pending_samples=5)],
            tests=[CustomerTopPendingTest(label_abbr="HEM", pending_tests=12)],
        ),
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_customer_orders_summary",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/customers/orders/summary?customer_id=742")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metrics"]["open_orders"] == 4
    assert body["orders"][0]["order_id"] == 90124


def test_customer_orders_summary_matches(monkeypatch):
    response_payload = CustomerOrdersSummaryResponse(
        matches=[
            CustomerLookupMatch(id=742, name="La Casa de las Flores", alias="Casa Flores", match_score=0.9),
            CustomerLookupMatch(id=351, name="Flores del Valle", alias=None, match_score=0.7),
        ]
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_customer_orders_summary",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/customers/orders/summary?customer_name=Casa&match_strategy=all")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matches"]) == 2
    assert data["matches"][0]["id"] == 742


def test_samples_overview_endpoint(monkeypatch):
    response_payload = SamplesOverviewResponse(
        kpis=SamplesOverviewKPI(total_samples=10, completed_samples=6, pending_samples=4),
        by_state=[SamplesDistributionItem(key="completed", count=6)],
        by_matrix_type=[SamplesDistributionItem(key="Saliva", count=4)],
        created_vs_completed=[
            SamplesDistributionItem(key="created", count=10),
            SamplesDistributionItem(key="completed", count=6),
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_samples_overview",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/samples/overview")
    assert resp.status_code == 200
    assert resp.json()["kpis"]["total_samples"] == 10


def test_tests_overview_endpoint(monkeypatch):
    response_payload = TestsOverviewResponse(
        kpis=TestsOverviewKPI(total_tests=5, completed_tests=3, pending_tests=2),
        by_state=[TestsDistributionItem(key="reported", count=3)],
        by_label=[TestsDistributionItem(key="PCR", count=2)],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_tests_overview",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/tests/overview")
    assert resp.status_code == 200
    assert resp.json()["kpis"]["completed_tests"] == 3


def test_tests_tat_endpoint(monkeypatch):
    response_payload = TestsTATResponse(
        metrics=TestsTATMetrics(
            average_hours=42,
            median_hours=40,
            p95_hours=60,
            completed_within_sla=8,
            completed_beyond_sla=2,
        ),
        distribution=[
            TestsTATDistributionBucket(label="0-24h", count=3),
            TestsTATDistributionBucket(label="24-48h", count=4),
        ],
        series=[TimeSeriesPoint(period_start=date(2025, 10, 12), value=36.5)],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_tests_tat",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/tests/tat?group_by=day")
    assert resp.status_code == 200
    assert resp.json()["metrics"]["average_hours"] == 42


def test_tests_tat_breakdown_endpoint(monkeypatch):
    response_payload = TestsTATBreakdownResponse(
        breakdown=[
            TestsTATBreakdownItem(
                label="PCR",
                average_hours=36,
                median_hours=34,
                p95_hours=55,
                total_tests=10,
            )
        ]
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_tests_tat_breakdown",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/tests/tat-breakdown")
    assert resp.status_code == 200
    assert resp.json()["breakdown"][0]["label"] == "PCR"


def test_metrics_filters_endpoint(monkeypatch):
    response_payload = MetricsFiltersResponse(
        customers=[{"id": 1, "name": "Acme"}],
        sample_states=["received"],
        test_states=["complete"],
        last_updated_at=None,
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_metrics_filters",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/common/filters")
    assert resp.status_code == 200
    assert resp.json()["customers"][0]["name"] == "Acme"


def test_tests_label_distribution_endpoint(monkeypatch):
    response_payload = TestsLabelDistributionResponse(
        labels=[
            TestsLabelCountItem(label="CN", count=40),
            TestsLabelCountItem(label="PS", count=25),
        ]
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.metrics.get_tests_label_distribution",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/metrics/tests/label-distribution")
    assert resp.status_code == 200
    assert resp.json()["labels"][0]["label"] == "CN"


def test_orders_throughput_endpoint(monkeypatch):
    response_payload = OrdersThroughputResponse(
        interval="week",
        points=[
            OrdersThroughputPoint(
                period_start=date(2025, 10, 12),
                orders_created=8,
                orders_completed=6,
                average_completion_hours=48.0,
                median_completion_hours=36.0,
            )
        ],
        totals=OrdersThroughputTotals(
            orders_created=8,
            orders_completed=6,
            average_completion_hours=48.0,
            median_completion_hours=36.0,
        ),
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_orders_throughput",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/orders/throughput?interval=week")
    assert resp.status_code == 200
    assert resp.json()["totals"]["orders_created"] == 8


def test_samples_cycle_time_endpoint(monkeypatch):
    response_payload = SamplesCycleTimeResponse(
        interval="day",
        points=[
            SamplesCycleTimePoint(
                period_start=date(2025, 10, 16),
                completed_samples=5,
                average_cycle_hours=30.0,
                median_cycle_hours=28.0,
            )
        ],
        totals=SamplesCycleTimeTotals(
            completed_samples=5,
            average_cycle_hours=30.0,
            median_cycle_hours=28.0,
        ),
        by_matrix_type=[
            SamplesCycleMatrixItem(
                matrix_type="Cured Flower",
                completed_samples=3,
                average_cycle_hours=32.0,
            )
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_samples_cycle_time",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/samples/cycle-time")
    assert resp.status_code == 200
    assert resp.json()["by_matrix_type"][0]["matrix_type"] == "Cured Flower"


def test_orders_funnel_endpoint(monkeypatch):
    response_payload = OrdersFunnelResponse(
        total_orders=12,
        stages=[
            OrdersFunnelStage(stage="created", count=12),
            OrdersFunnelStage(stage="received", count=9),
            OrdersFunnelStage(stage="completed", count=7),
            OrdersFunnelStage(stage="reported", count=5),
            OrdersFunnelStage(stage="on_hold", count=2),
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_orders_funnel",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/orders/funnel")
    assert resp.status_code == 200
    assert resp.json()["stages"][0]["stage"] == "created"


def test_orders_slowest_endpoint(monkeypatch):
    response_payload = OrdersSlowestResponse(
        items=[
            SlowOrderItem(
                order_id=101,
                order_reference="bucket-2025-10-06",
                customer_name="Aggregate",
                state="completed",
                completion_hours=114.0,
                age_hours=115.0,
                date_created=datetime(2025, 10, 6, 12, 0, 0),
                date_completed=datetime(2025, 10, 11, 10, 0, 0),
            )
        ]
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_slowest_orders",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/orders/slowest?limit=3")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["order_reference"] == "bucket-2025-10-06"


def test_priority_orders_slowest_endpoint(monkeypatch):
    response_payload = SlowReportedOrdersResponse(
        stats=SlowReportedOrdersStats(
            total_orders=2,
            average_open_hours=90.0,
            percentile_95_open_hours=120.0,
            threshold_hours=96.0,
        ),
        items=[
            SlowReportedOrderItem(
                order_id=901,
                order_reference="ORD-901",
                customer_name="Slow Labs",
                date_created=datetime(2025, 10, 1, 8, 0, 0),
                date_reported=datetime(2025, 10, 6, 10, 0, 0),
                samples_count=4,
                tests_count=12,
                open_time_hours=122.0,
                open_time_label="5d 2h",
                is_outlier=True,
            )
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_priority_slowest_reported_orders",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/priority-orders/slowest?min_open_hours=72")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"][0]["open_time_label"] == "5d 2h"
    assert payload["stats"]["total_orders"] == 2


def test_orders_overdue_endpoint(monkeypatch):
    response_payload = OverdueOrdersResponse(
        interval="week",
        minimum_days_overdue=30,
        warning_window_days=5,
        sla_hours=72.0,
        kpis=OverdueOrdersKpis(
            total_overdue=12,
            average_open_hours=850.5,
            max_open_hours=1200.0,
            percent_overdue_vs_active=0.6,
            overdue_beyond_sla=8,
            overdue_within_sla=4,
        ),
        top_orders=[
            OverdueOrderItem(
                order_id=501,
                custom_formatted_id="ORD-501",
                customer_id=42,
                customer_name="Arcanna LLC",
                state="ON HOLD",
                date_created=datetime(2025, 8, 15, 9, 30),
                open_hours=1200.0,
                total_samples=10,
                incomplete_sample_count=2,
                incomplete_samples=[
                    OverdueSampleDetail(
                        sample_id=7001,
                        sample_custom_id="S-7001",
                        sample_name="Sample Alpha",
                        matrix_type="Flower",
                        total_tests=8,
                        incomplete_tests=3,
                        tests=[
                            OverdueTestDetail(
                                primary_test_id=9101,
                                test_ids=[9101],
                                label_abbr="THC",
                                states=["IN PROGRESS"],
                            )
                        ],
                    )
                ],
            )
        ],
        clients=[
            OverdueClientSummary(
                customer_id=42,
                customer_name="Arcanna LLC",
                overdue_orders=7,
                total_open_hours=4500.0,
                average_open_hours=642.8,
                max_open_hours=1200.0,
            )
        ],
        warning_orders=[
            OverdueOrderItem(
                order_id=610,
                custom_formatted_id="ORD-610",
                customer_id=77,
                customer_name="North Labs",
                state="IN PROGRESS",
                date_created=datetime(2025, 9, 25, 10, 0),
                open_hours=650.0,
            )
        ],
        timeline=[
            OverdueTimelinePoint(
                period_start=date(2025, 10, 6),
                overdue_orders=5,
            )
        ],
        heatmap=[
            OverdueHeatmapCell(
                customer_id=42,
                customer_name="Arcanna LLC",
                period_start=date(2025, 10, 6),
                overdue_orders=3,
            )
        ],
        state_breakdown=[
            OverdueStateBreakdown(state="ON HOLD", count=8, ratio=0.6667),
            OverdueStateBreakdown(state="IN PROGRESS", count=4, ratio=0.3333),
        ],
        ready_to_report_samples=[
            ReadyToReportSampleItem(
                sample_id=9001,
                sample_name="Sample R",
                sample_custom_id="S-9001",
                order_id=501,
                order_custom_id="ORD-501",
                customer_id=42,
                customer_name="Arcanna LLC",
                date_created=datetime(2025, 10, 1, 8, 0),
                completed_date=datetime(2025, 10, 5, 12, 0),
                tests_ready_count=3,
                tests_total_count=3,
            )
        ],
        metrc_samples=[
            MetrcSampleStatusItem(
                sample_id=8001,
                sample_custom_id="S-8001",
                date_created=datetime(2025, 9, 28, 10, 0),
                metrc_id="1A40D030000A5A1000000550",
                metrc_status="RECEIVED",
                metrc_date=datetime(2025, 9, 30, 9, 0),
            ),
            MetrcSampleStatusItem(
                sample_id=8002,
                sample_custom_id="S-8002",
                date_created=datetime(2025, 9, 29, 11, 0),
                metrc_id="1A40D030000A5A1000000551",
                metrc_status="PROCESSING",
                metrc_date=datetime(2025, 10, 1, 8, 30),
            ),
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_overdue_orders",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/orders/overdue?min_days_overdue=30")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kpis"]["total_overdue"] == 12
    assert body["top_orders"][0]["order_id"] == 501
    assert body["top_orders"][0]["total_samples"] == 10
    assert body["top_orders"][0]["incomplete_samples"][0]["tests"][0]["states"][0] == "IN PROGRESS"
    assert body["ready_to_report_samples"][0]["sample_custom_id"] == "S-9001"
    assert len(body["metrc_samples"]) == 2
    assert body["metrc_samples"][0]["metrc_id"] == "1A40D030000A5A1000000550"


def test_customers_alerts_endpoint(monkeypatch):
    response_payload = CustomerAlertsResponse(
        interval="week",
        sla_hours=48.0,
        min_alert_percentage=0.1,
        heatmap=[
            CustomerHeatmapPoint(
                customer_id=1,
                customer_name="Acme Labs",
                period_start=date(2025, 10, 6),
                total_tests=10,
                on_hold_tests=2,
                not_reportable_tests=1,
                sla_breach_tests=3,
                on_hold_ratio=0.2,
                not_reportable_ratio=0.1,
                sla_breach_ratio=0.3,
            )
        ],
        alerts=[
            CustomerAlertItem(
                customer_id=1,
                customer_name="Acme Labs",
                orders_total=5,
                orders_on_hold=1,
                orders_beyond_sla=1,
                tests_total=10,
                tests_on_hold=2,
                tests_not_reportable=1,
                tests_beyond_sla=3,
                primary_reason="tests_beyond_sla",
                primary_ratio=0.3,
                latest_activity_at=datetime(2025, 10, 6, 12, 0, 0),
            )
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_customer_alerts",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/customers/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["alerts"][0]["customer_name"] == "Acme Labs"
    assert data["heatmap"][0]["on_hold_tests"] == 2


def test_tests_state_distribution_endpoint(monkeypatch):
    response_payload = TestsStateDistributionResponse(
        interval="week",
        states=["ON HOLD", "REPORTED"],
        series=[
            TestStatePoint(
                period_start=date(2025, 10, 6),
                total_tests=6,
                buckets=[
                    TestStateBucket(state="ON HOLD", count=2, ratio=0.3333),
                    TestStateBucket(state="REPORTED", count=4, ratio=0.6667),
                ],
            )
        ],
        totals=[
            TestStateBucket(state="ON HOLD", count=2, ratio=0.3333),
            TestStateBucket(state="REPORTED", count=4, ratio=0.6667),
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_tests_state_distribution",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/tests/state-distribution")
    assert resp.status_code == 200
    assert resp.json()["states"] == ["ON HOLD", "REPORTED"]


def test_quality_kpis_endpoint(monkeypatch):
    response_payload = QualityKpisResponse(
        sla_hours=48.0,
        tests=QualityKpiTests(
            total_tests=20,
            on_hold_tests=3,
            not_reportable_tests=1,
            cancelled_tests=2,
            reported_tests=10,
            within_sla_tests=12,
            beyond_sla_tests=8,
            on_hold_ratio=0.15,
            not_reportable_ratio=0.05,
            beyond_sla_ratio=0.4,
        ),
        orders=QualityKpiOrders(
            total_orders=8,
            on_hold_orders=1,
            completed_orders=6,
            within_sla_orders=5,
            beyond_sla_orders=3,
            on_hold_ratio=0.125,
            beyond_sla_ratio=0.375,
        ),
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.analytics.get_quality_kpis",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/analytics/kpis/quality")
    assert resp.status_code == 200
    assert resp.json()["tests"]["total_tests"] == 20
    assert resp.json()["orders"]["beyond_sla_ratio"] == 0.375


def test_get_sample_detail(monkeypatch):
    response_payload = SampleDetailResponse(
        sample={
            "id": 1,
            "sample_name": "Sample A",
            "order_id": 10,
            "state": "completed",
            "sla_status": "ok",
            "sla_hours": 48,
        },
        order={"id": 10, "state": "completed"},
        tests=None,
        batches=[SampleBatchItem(id=5, display_name="Batch 1")],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.entities.entities_service.get_sample_detail",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/entities/samples/1")
    assert resp.status_code == 200
    assert resp.json()["sample"]["sample_name"] == "Sample A"


def test_get_sample_detail_not_found(monkeypatch):
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.entities.entities_service.get_sample_detail",
        lambda *args, **kwargs: None,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/entities/samples/999")
    assert resp.status_code == 404


def test_get_test_detail(monkeypatch):
    response_payload = TestDetailResponse(
        test={
            "id": 1,
            "label_abbr": "PCR",
            "state": "complete",
            "sla_status": "ok",
            "sla_hours": 48,
        },
        sample={"id": 1, "sample_name": "Sample A", "state": "complete"},
        order={"id": 10, "state": "completed"},
        batches=[TestBatchItem(id=5, display_name="Batch 1")],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.entities.entities_service.get_test_detail",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/entities/tests/1")
    assert resp.status_code == 200
    assert resp.json()["test"]["label_abbr"] == "PCR"


def test_get_test_detail_not_found(monkeypatch):
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.entities.entities_service.get_test_detail",
        lambda *args, **kwargs: None,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/entities/tests/999")
    assert resp.status_code == 404


def test_get_sample_detail_full(monkeypatch):
    response_payload = SampleDetailResponse(
        sample={
            "id": 2,
            "sample_name": "Full Sample",
            "order_id": 20,
            "state": "created",
            "sla_status": "warning",
            "sla_hours": 24,
        },
        order={"id": 20, "state": "created"},
        tests=[SampleTestItem(id=11, label_abbr="CN", state="WEIGHED", has_report=False)],
        batches=[SampleBatchItem(id=7, display_name="Batch 7")],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.entities.entities_service.get_sample_detail",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/entities/samples/2/full?include_tests=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample"]["sla_status"] == "warning"
    assert body["tests"][0]["label_abbr"] == "CN"


def test_get_test_detail_full(monkeypatch):
    response_payload = TestDetailResponse(
        test={"id": 555, "state": "WEIGHED", "sla_status": "overdue", "sla_hours": 36},
        sample={"id": 2, "sample_name": "Full Sample"},
        order={"id": 20, "state": "CREATED"},
        batches=[TestBatchItem(id=9, display_name="Batch X")],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.entities.entities_service.get_test_detail",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/entities/tests/555/full?sla_hours=36")
    assert resp.status_code == 200
    assert resp.json()["test"]["sla_status"] == "overdue"


def test_get_order_detail(monkeypatch):
    response_payload = OrderDetailResponse(
        order={
            "id": 3442,
            "state": "CREATED",
            "sla_status": "overdue",
            "sla_hours": 48,
            "pending_samples": 1,
        },
        customer={"id": 386},
        samples=[
            OrderSampleItem(
                id=16158,
                sample_name="Fruit Chew",
                state="CREATED",
                pending_tests=3,
                tests=[
                    OrderSampleTestItem(id=55506, label_abbr="CN", state="WEIGHED", has_report=False),
                ],
            )
        ],
    )
    monkeypatch.setattr(
        "downloader_qbench_data.api.routers.entities.entities_service.get_order_detail",
        lambda *args, **kwargs: response_payload,
    )
    client = create_test_client(monkeypatch)
    resp = client.get("/api/v1/entities/orders/3442?include_tests=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["order"]["id"] == 3442
    assert body["samples"][0]["tests"][0]["label_abbr"] == "CN"
