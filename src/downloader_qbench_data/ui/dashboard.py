"""Main PySide6 dashboard window."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .api_client import ApiClient
from .styles import GLOBAL_STYLE
from .widgets import (
    KpiCard,
    QualityHeatmapCard,
    SamplesTestsBarChart,
    TableCard,
    TatLineChart,
    TestsStateStackedBarChart,
    format_hours_to_days,
)


@dataclass
class DashboardConfig:
    api_base_url: str = os.environ.get("DASHBOARD_API_BASE_URL", "http://localhost:8000/api/v1")
    compare_previous: bool = True
    default_days: int = 7


class ApiWorker(QtCore.QRunnable):
    """Runs API calls in a background thread."""

    def __init__(self, fn, *args, **kwargs) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # pragma: no cover - propagation
            self.signals.error.emit(exc)
        else:
            self.signals.result.emit(result)


class WorkerSignals(QtCore.QObject):
    """Signals shared by ApiWorker."""

    result = QtCore.Signal(object)
    error = QtCore.Signal(Exception)


class DashboardWindow(QtWidgets.QMainWindow):
    """Main dashboard window."""

    def __init__(
        self,
        *,
        api_client: Optional[ApiClient] = None,
        config: Optional[DashboardConfig] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("QBench Dashboard")
        self.resize(1280, 900)
        self.setStyleSheet(GLOBAL_STYLE)

        self.config = config or DashboardConfig()
        self.api_client = api_client or ApiClient(self.config.api_base_url)
        self.thread_pool = QtCore.QThreadPool.globalInstance()

        # Date range controls -------------------------------------------------
        self.date_from_edit = QtWidgets.QDateEdit(self)
        self.date_from_edit.setCalendarPopup(True)
        self.date_from_edit.setDisplayFormat("yyyy-MM-dd")

        self.date_to_edit = QtWidgets.QDateEdit(self)
        self.date_to_edit.setCalendarPopup(True)
        self.date_to_edit.setDisplayFormat("yyyy-MM-dd")

        self.refresh_button = QtWidgets.QPushButton("Refresh", self)
        self.refresh_button.setObjectName("PrimaryButton")
        self.refresh_button.clicked.connect(self.reload_data)

        today = date.today()
        default_start = today - timedelta(days=self.config.default_days - 1)
        self.date_from_edit.setDate(QtCore.QDate(default_start.year, default_start.month, default_start.day))
        self.date_to_edit.setDate(QtCore.QDate(today.year, today.month, today.day))

        # KPI Cards -----------------------------------------------------------
        self.samples_card = KpiCard("Samples")
        self.tests_card = KpiCard("Tests")
        self.customers_card = KpiCard("Customers")
        self.reports_card = KpiCard("Reports")
        self.tat_card = KpiCard("Avg TAT (hrs)")

        # Quality KPI Cards ---------------------------------------------------
        self.quality_tests_card = KpiCard("Tests")
        self.quality_on_hold_card = KpiCard("Tests ON HOLD")
        self.quality_breach_card = KpiCard("Tests > SLA")
        self.quality_orders_on_hold_card = KpiCard("Orders ON HOLD")

        # Charts / Tables -----------------------------------------------------
        self.bar_chart = SamplesTestsBarChart()
        self.new_customers_table = TableCard("New customers", ["ID", "Name", "Created"])
        self.top_customers_table = TableCard("Top customers with tests", ["ID", "Name", "Tests"])
        self.tat_chart = TatLineChart()

        # Quality widgets -----------------------------------------------------
        self.quality_heatmap = QualityHeatmapCard("Critical states heatmap")
        self.quality_state_chart = TestsStateStackedBarChart("Tests by state")
        self.quality_alerts_table = TableCard(
            "Customer alerts",
            ["Customer", "Orders", "Tests", "Primary alert", "Ratio", "Latest activity"],
        )

        # Summary label -------------------------------------------------------
        self.last_update_label = QtWidgets.QLabel("", self)
        self.last_update_label.setObjectName("SubtitleLabel")

        # Layout --------------------------------------------------------------
        container = QtWidgets.QWidget()
        container.setObjectName("DashboardContainer")
        main_layout = QtWidgets.QVBoxLayout(container)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # Filters
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.setSpacing(12)
        filter_layout.addWidget(QtWidgets.QLabel("From:", self))
        filter_layout.addWidget(self.date_from_edit)
        filter_layout.addWidget(QtWidgets.QLabel("To:", self))
        filter_layout.addWidget(self.date_to_edit)
        filter_layout.addStretch(1)
        filter_layout.addWidget(self.refresh_button)
        main_layout.addLayout(filter_layout)
        main_layout.addWidget(self.last_update_label)

        # Tabs ----------------------------------------------------------------
        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.setObjectName("DashboardTabs")
        main_layout.addWidget(self.tabs, 1)

        self.operational_tab = self._build_operational_tab()
        self.tabs.addTab(self.operational_tab, "Operational Efficiency")

        self.quality_tab = self._build_quality_tab()
        self.tabs.addTab(self.quality_tab, "Quality & SLA Monitor")

        self.setCentralWidget(container)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Loading data…")

        QtCore.QTimer.singleShot(100, self.reload_data)

    # ------------------------------------------------------------------ API --

    def _build_operational_tab(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setSpacing(16)

        kpi_layout = QtWidgets.QHBoxLayout()
        kpi_layout.setSpacing(16)
        for card in (self.samples_card, self.tests_card, self.customers_card, self.reports_card, self.tat_card):
            card.setMinimumWidth(150)
            kpi_layout.addWidget(card)
        layout.addLayout(kpi_layout)

        layout.addWidget(self.bar_chart)

        tables_layout = QtWidgets.QHBoxLayout()
        tables_layout.setSpacing(16)
        tables_layout.addWidget(self.new_customers_table)
        tables_layout.addWidget(self.top_customers_table)
        layout.addLayout(tables_layout)

        self.tat_chart.setMinimumHeight(320)
        layout.addWidget(self.tat_chart)
        layout.addStretch(1)

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def _build_quality_tab(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setSpacing(16)

        kpi_layout = QtWidgets.QHBoxLayout()
        kpi_layout.setSpacing(16)
        for card in (
            self.quality_tests_card,
            self.quality_on_hold_card,
            self.quality_breach_card,
            self.quality_orders_on_hold_card,
        ):
            card.setMinimumWidth(150)
            kpi_layout.addWidget(card)
        layout.addLayout(kpi_layout)

        charts_layout = QtWidgets.QHBoxLayout()
        charts_layout.setSpacing(16)
        charts_layout.addWidget(self.quality_heatmap)
        charts_layout.addWidget(self.quality_state_chart)
        layout.addLayout(charts_layout)

        layout.addWidget(self.quality_alerts_table)
        layout.addStretch(1)

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def _current_date_range(self) -> tuple[date, date]:
        start = self.date_from_edit.date().toPython()
        end = self.date_to_edit.date().toPython()
        return start, end

    def reload_data(self) -> None:
        start, end = self._current_date_range()
        self.status_bar.showMessage("Refreshing dashboard…", 2000)
        self._run_api(self.api_client.fetch_summary, self._handle_summary, date_from=start, date_to=end)
        self._run_api(
            self.api_client.fetch_daily_activity,
            self._handle_daily_activity,
            date_from=start,
            date_to=end,
            compare_previous=self.config.compare_previous,
        )
        self._run_api(
            self.api_client.fetch_new_customers,
            self._handle_new_customers,
            date_from=start,
            date_to=end,
            limit=10,
        )
        self._run_api(
            self.api_client.fetch_top_customers,
            self._handle_top_customers,
            date_from=start,
            date_to=end,
            limit=10,
        )
        self._run_api(
            self.api_client.fetch_reports_overview,
            self._handle_reports_overview,
            date_from=start,
            date_to=end,
        )
        self._run_api(
            self.api_client.fetch_tat_daily,
            self._handle_tat_daily,
            date_from=start,
            date_to=end,
        )
        self._run_api(
            self.api_client.fetch_customer_alerts,
            self._handle_customer_alerts,
            date_from=start,
            date_to=end,
        )
        self._run_api(
            self.api_client.fetch_tests_state_distribution,
            self._handle_tests_state_distribution,
            date_from=start,
            date_to=end,
        )
        self._run_api(
            self.api_client.fetch_quality_kpis,
            self._handle_quality_kpis,
            date_from=start,
            date_to=end,
        )

    def _run_api(self, fn, callback, *args, **kwargs) -> None:
        worker = ApiWorker(fn, *args, **kwargs)
        worker.signals.result.connect(callback)
        worker.signals.error.connect(self._handle_error)
        self.thread_pool.start(worker)

    # -------------------------------------------------------------- Handlers --
    def _handle_summary(self, payload: dict) -> None:
        kpis = payload.get("kpis") or {}
        self.samples_card.update_value(str(kpis.get("total_samples", "--")))
        self.tests_card.update_value(str(kpis.get("total_tests", "--")))
        self.customers_card.update_value(str(kpis.get("total_customers", "--")))
        self.reports_card.update_value(str(kpis.get("total_reports", "--")))
        avg_tat = kpis.get("average_tat_hours")
        self.tat_card.update_value(format_hours_to_days(avg_tat))

        last_updated = payload.get("last_updated_at")
        if isinstance(last_updated, datetime):
            self.last_update_label.setText(f"Last update: {last_updated.isoformat(sep=' ', timespec='minutes')}")
        else:
            self.last_update_label.setText("")

    def _handle_daily_activity(self, payload: dict) -> None:
        samples = payload.get("current_samples", {})
        tests = payload.get("current_tests", {})
        self.bar_chart.update_data(samples, tests)

    def _handle_new_customers(self, customers: list[dict]) -> None:
        rows = [
            (
                customer.get("id"),
                customer.get("name"),
                customer.get("created_at").strftime("%Y-%m-%d %H:%M") if customer.get("created_at") else "",
            )
            for customer in customers
        ]
        self.new_customers_table.update_rows(rows)

    def _handle_top_customers(self, customers: list[dict]) -> None:
        rows = [
            (
                customer.get("id"),
                customer.get("name"),
                customer.get("tests"),
            )
            for customer in customers
        ]
        self.top_customers_table.update_rows(rows)

    def _handle_reports_overview(self, payload: dict) -> None:
        total = payload.get("total_reports", 0)
        within = payload.get("reports_within_sla", 0)
        beyond = payload.get("reports_beyond_sla", 0)
        total_str = f"{total} total (within SLA: {within}, beyond: {beyond})"
        self.reports_card.update_value(str(total), caption=total_str)

    def _handle_tat_daily(self, payload: dict) -> None:
        points = sorted(
            (
                item["date"],
                item.get("average_hours"),
                item.get("within_sla", 0),
                item.get("beyond_sla", 0),
            )
            for item in payload.get("points", [])
            if item.get("date")
        )
        if not points:
            self.tat_chart.update_data([], [])
            return

        moving = sorted(
            (item["period_start"], item.get("value"))
            for item in payload.get("moving_average_hours", [])
            if item.get("period_start") and item.get("value") is not None
        )
        self.tat_chart.update_data(points, moving)

    def _handle_customer_alerts(self, payload: dict) -> None:
        heatmap_points = payload.get("heatmap", [])
        self.quality_heatmap.update_data(heatmap_points)

        alerts = payload.get("alerts", [])
        rows = []
        for alert in alerts:
            customer = alert.get("customer_name") or f"Customer {alert.get('customer_id')}"
            orders_total = alert.get("orders_total", 0)
            orders_on_hold = alert.get("orders_on_hold", 0)
            tests_total = alert.get("tests_total", 0)
            tests_on_hold = alert.get("tests_on_hold", 0)
            tests_not_reportable = alert.get("tests_not_reportable", 0)
            tests_beyond_sla = alert.get("tests_beyond_sla", 0)
            primary_reason = alert.get("primary_reason", "")
            primary_ratio = alert.get("primary_ratio", 0.0)
            latest = alert.get("latest_activity_at")
            latest_str = latest.strftime("%Y-%m-%d %H:%M") if isinstance(latest, datetime) else ""
            tests_summary = f"{tests_total} (OH {tests_on_hold}, NR {tests_not_reportable}, >SLA {tests_beyond_sla})"
            orders_summary = f"{orders_total} (OH {orders_on_hold})"
            rows.append(
                (
                    customer,
                    orders_summary,
                    tests_summary,
                    primary_reason.replace("_", " ").title(),
                    f"{primary_ratio:.1%}",
                    latest_str,
                )
            )
        self.quality_alerts_table.update_rows(rows)

    def _handle_tests_state_distribution(self, payload: dict) -> None:
        states = payload.get("states", [])
        series = payload.get("series", [])
        self.quality_state_chart.update_data(series, states)

    def _handle_quality_kpis(self, payload: dict) -> None:
        tests = payload.get("tests", {})
        orders = payload.get("orders", {})

        def _fmt_ratio(value: Optional[float]) -> str:
            return f"{value:.1%}" if value is not None else "--"

        self.quality_tests_card.update_value(str(tests.get("total_tests", "--")))
        self.quality_on_hold_card.update_value(
            str(tests.get("on_hold_tests", "--")),
            caption=f"{_fmt_ratio(tests.get('on_hold_ratio'))} of tests",
        )
        self.quality_breach_card.update_value(
            str(tests.get("beyond_sla_tests", "--")),
            caption=f"{_fmt_ratio(tests.get('beyond_sla_ratio'))} of tests",
        )
        self.quality_orders_on_hold_card.update_value(
            str(orders.get("on_hold_orders", "--")),
            caption=f"{_fmt_ratio(orders.get('on_hold_ratio'))} of orders",
        )

    def _handle_error(self, error: Exception) -> None:  # pragma: no cover - UI feedback
        self.status_bar.showMessage(f"Failed to update dashboard: {error}", 5000)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802 - Qt signature
        try:
            self.api_client.close()
        except Exception:  # pragma: no cover
            pass
        super().closeEvent(event)


__all__ = ["DashboardWindow", "DashboardConfig"]
