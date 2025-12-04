"""Custom widgets used by the dashboard."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional, Sequence

from PySide6 import QtCharts, QtCore, QtGui, QtWidgets


def format_hours_to_days(hours: Optional[float]) -> str:
    """Convert decimal hours to ``Xd Yh`` representation."""

    if hours is None or hours <= 0:
        return "--"
    total_hours = int(hours)
    days, rem_hours = divmod(total_hours, 24)
    if days:
        return f"{days} d {rem_hours} h"
    return f"{rem_hours} h"


class KpiCard(QtWidgets.QFrame):
    """Simple card showing a KPI value and label."""

    def __init__(self, title: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(90)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self.title_label = QtWidgets.QLabel(title, self)
        self.title_label.setObjectName("SubtitleLabel")

        self.value_label = QtWidgets.QLabel("--", self)
        self.value_label.setObjectName("ValueLabel")

        self.caption_label = QtWidgets.QLabel("", self)
        self.caption_label.setObjectName("SubtitleLabel")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)
        layout.addStretch(1)

    def update_value(self, value: str, caption: str | None = None) -> None:
        self.value_label.setText(value)
        if caption:
            self.caption_label.setText(caption)
            self.caption_label.show()
        else:
            self.caption_label.hide()


class ChartCard(QtWidgets.QFrame):
    """Base card containing a chart view."""

    def __init__(self, title: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title_label = QtWidgets.QLabel(title, self)
        title_label.setObjectName("SubtitleLabel")
        layout.addWidget(title_label)

        self.chart = QtCharts.QChart()
        self.chart.legend().setVisible(True)
        self.chart.legend().setLabelColor(QtGui.QColor("#d7e2f3"))
        self.chart.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 0)))
        self.chart.setTitleBrush(QtGui.QBrush(QtGui.QColor("#d7e2f3")))
        self.chart.setTitle("")

        self.chart_view = QtCharts.QChartView(self.chart, self)
        self.chart_view.setRenderHint(QtGui.QPainter.Antialiasing)
        layout.addWidget(self.chart_view)


class SamplesTestsBarChart(ChartCard):
    """Bar chart comparing samples vs tests per day."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__("Samples vs Tests", parent)

        self.chart_view.setMinimumHeight(320)

        self.samples_set = QtCharts.QBarSet("Samples")
        self.samples_set.setColor(QtGui.QColor("#4C6EF5"))
        self.tests_set = QtCharts.QBarSet("Tests")
        self.tests_set.setColor(QtGui.QColor("#7EE787"))

        self.bar_series = QtCharts.QBarSeries()
        self.bar_series.append(self.samples_set)
        self.bar_series.append(self.tests_set)
        self.bar_series.setBarWidth(0.4)
        self.chart.addSeries(self.bar_series)

        self.categories_axis = QtCharts.QBarCategoryAxis()
        self.categories_axis.setLabelsColor(QtGui.QColor("white"))
        self.categories_axis.setTitleText("Fecha")
        self.categories_axis.setTitleBrush(QtGui.QBrush(QtGui.QColor("white")))

        self.value_axis = QtCharts.QValueAxis()
        self.value_axis.setLabelFormat("%d")
        self.value_axis.setTitleText("Conteo")
        self.value_axis.setLabelsColor(QtGui.QColor("white"))
        self.value_axis.setTitleBrush(QtGui.QBrush(QtGui.QColor("white")))

        self.chart.addAxis(self.categories_axis, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.value_axis, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.bar_series.attachAxis(self.categories_axis)
        self.bar_series.attachAxis(self.value_axis)

        self.bar_series.hovered.connect(self._on_bar_hover)

    def update_data(self, samples: dict[date, int], tests: dict[date, int]) -> None:
        self.samples_set.remove(0, self.samples_set.count())
        self.tests_set.remove(0, self.tests_set.count())
        self.categories_axis.clear()

        categories = sorted(set(samples.keys()) | set(tests.keys()))
        if not categories:
            today_label = date.today().strftime("%b %d")
            self.categories_axis.append([today_label])
            self.samples_set.append(0.0)
            self.tests_set.append(0.0)
            self.value_axis.setRange(0, 1)
            return

        max_value = 1
        labels: list[str] = []
        for day in categories:
            labels.append(day.strftime("%b %d"))
            sample_value = float(samples.get(day, 0))
            test_value = float(tests.get(day, 0))
            self.samples_set.append(sample_value)
            self.tests_set.append(test_value)
            max_value = max(max_value, sample_value, test_value)

        self.categories_axis.append(labels)
        self.bar_series.setBarWidth(0.4 if len(labels) <= 12 else 0.25)
        self.value_axis.setRange(0, max_value + 1)

    def _on_bar_hover(self, status: bool, index: int, bar_set: QtCharts.QBarSet) -> None:
        if not status or index < 0:
            QtWidgets.QToolTip.hideText()
            return
        categories = getattr(self.categories_axis, "categories", lambda: [])()
        if not categories or index >= len(categories):
            QtWidgets.QToolTip.hideText()
            return
        category = categories[index]
        value = int(bar_set.at(index))
        label = bar_set.label() or ""
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), f"{label}: {value} ({category})", self.chart_view)


class TatLineChart(ChartCard):
    """Line chart for TAT trend, including moving average."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__("Daily TAT Trend", parent)

        self.chart_view.setMinimumHeight(320)

        self.average_series = QtCharts.QLineSeries()
        self.average_series.setName("Daily avg (hours)")
        self.average_series.setColor(QtGui.QColor("#3c6ef5"))
        self.average_series.setPointsVisible(True)

        self.moving_avg_series = QtCharts.QLineSeries()
        self.moving_avg_series.setName("Moving avg")
        self.moving_avg_series.setColor(QtGui.QColor("#ffaa44"))
        self.moving_avg_series.setPointsVisible(False)

        self.chart.addSeries(self.average_series)
        self.chart.addSeries(self.moving_avg_series)

        self.date_axis = QtCharts.QDateTimeAxis()
        self.date_axis.setFormat("MMM dd")
        self.chart.addAxis(self.date_axis, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.average_series.attachAxis(self.date_axis)
        self.moving_avg_series.attachAxis(self.date_axis)

        self.value_axis = QtCharts.QValueAxis()
        self.value_axis.setTitleText("Hours")
        self.value_axis.setLabelFormat("%.1f")
        self.chart.addAxis(self.value_axis, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.average_series.attachAxis(self.value_axis)
        self.moving_avg_series.attachAxis(self.value_axis)

        self.average_series.hovered.connect(self._on_point_hover)

    def update_data(
        self,
        points: Iterable[tuple[date, Optional[float], int, int]],
        moving_avg: Iterable[tuple[date, float]],
    ) -> None:
        points = list(points)
        moving_avg = list(moving_avg)

        self.average_series.clear()
        self.moving_avg_series.clear()
        self._point_data = {}

        if not points:
            now = QtCore.QDateTime.currentDateTime()
            self.date_axis.setRange(now.addDays(-7), now)
            self.value_axis.setRange(0, 1)
            return

        def _to_qdatetime(day: date) -> QtCore.QDateTime:
            return QtCore.QDateTime(QtCore.QDate(day.year, day.month, day.day), QtCore.QTime(0, 0, 0))

        max_hours = 1.0
        min_dt: Optional[QtCore.QDateTime] = None
        max_dt: Optional[QtCore.QDateTime] = None

        self._point_data: dict[int, tuple[float, int, int]] = {}

        meaningful_points = [item for item in points if item[1] is not None]
        for day, avg_hours, within, beyond in meaningful_points:
            dt = _to_qdatetime(day)
            ms = dt.toMSecsSinceEpoch()
            self.average_series.append(ms, avg_hours)
            self._point_data[ms] = (avg_hours or 0.0, within, beyond)
            max_hours = max(max_hours, avg_hours)
            if min_dt is None or dt < min_dt:
                min_dt = dt
            if max_dt is None or dt > max_dt:
                max_dt = dt

        for day, avg in moving_avg:
            if avg is None:
                continue
            dt = _to_qdatetime(day)
            self.moving_avg_series.append(dt.toMSecsSinceEpoch(), avg)
            max_hours = max(max_hours, avg)
            if min_dt is None or dt < min_dt:
                min_dt = dt
            if max_dt is None or dt > max_dt:
                max_dt = dt

        if not meaningful_points:
            now = QtCore.QDateTime.currentDateTime()
            self.date_axis.setRange(now.addDays(-7), now)
            self.value_axis.setRange(0, 1)
            return

        if min_dt and max_dt:
            self.date_axis.setRange(min_dt, max_dt)
        else:
            now = QtCore.QDateTime.currentDateTime()
            self.date_axis.setRange(now.addDays(-7), now)
        self.value_axis.setRange(0, max_hours * 1.2 if max_hours else 1.0)

    def _on_point_hover(self, point: QtCore.QPointF, state: bool) -> None:
        if not state:
            QtWidgets.QToolTip.hideText()
            return
        ms = int(point.x())
        data = getattr(self, "_point_data", {}).get(ms)
        if not data:
            return
        hours, within, beyond = data
        text = f"{format_hours_to_days(hours)}\nWithin SLA: {within}\nBeyond SLA: {beyond}"
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), text, self.chart_view)


class TableCard(QtWidgets.QFrame):
    """Displays tabular information in a styled table."""

    def __init__(
        self,
        title: str,
        headers: Iterable[str],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title_label = QtWidgets.QLabel(title, self)
        title_label.setObjectName("SubtitleLabel")
        layout.addWidget(title_label)

        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(len(list(headers)))
        self.table.setHorizontalHeaderLabels(list(headers))
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(200)
        layout.addWidget(self.table)

    def update_rows(self, rows: Iterable[Iterable[str]]) -> None:
        values = list(rows)
        self.table.setRowCount(len(values))
        for row_index, row in enumerate(values):
            for col_index, value in enumerate(row):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(row_index, col_index, item)


def _ratio_color(ratio: float) -> QtGui.QColor:
    ratio = max(0.0, min(float(ratio), 1.0))
    color = QtGui.QColor()
    saturation = int(200 * ratio)
    value = 255 - int(80 * ratio)
    color.setHsv(0, saturation, value)
    return color


class QualityHeatmapCard(QtWidgets.QFrame):
    """Heatmap table showing quality ratios over time."""

    def __init__(self, title: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title_label = QtWidgets.QLabel(title, self)
        title_label.setObjectName("SubtitleLabel")
        layout.addWidget(title_label)

        self.table = QtWidgets.QTableWidget(self)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

    def update_data(self, points: Sequence[dict]) -> None:
        customers = {}
        periods: list[date] = []
        for point in points:
            period = point.get("period_start")
            customer_id = point.get("customer_id")
            if not period or customer_id is None:
                continue
            customers.setdefault(customer_id, {"name": point.get("customer_name"), "data": {}})
            customers[customer_id]["data"][period] = point
            if period not in periods:
                periods.append(period)

        periods.sort()
        customer_rows = sorted(customers.items(), key=lambda item: (item[1]["name"] or "").lower())

        column_count = 1 + len(periods)
        self.table.setColumnCount(column_count)
        headers = ["Customer"] + [period.strftime("%Y-%m-%d") for period in periods]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(customer_rows))

        for row_index, (customer_id, info) in enumerate(customer_rows):
            name = info.get("name") or f"Customer {customer_id}"
            first_item = QtWidgets.QTableWidgetItem(name)
            first_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row_index, 0, first_item)

            for col_index, period in enumerate(periods, start=1):
                point = info["data"].get(period)
                item = QtWidgets.QTableWidgetItem("--")
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                if point:
                    total = int(point.get("total_tests") or 0)
                    on_hold = int(point.get("on_hold_tests") or 0)
                    not_reportable = int(point.get("not_reportable_tests") or 0)
                    beyond_sla = int(point.get("sla_breach_tests") or 0)
                    max_ratio = max(
                        float(point.get("on_hold_ratio") or 0.0),
                        float(point.get("not_reportable_ratio") or 0.0),
                        float(point.get("sla_breach_ratio") or 0.0),
                    )
                    if total > 0:
                        item.setText(
                            f"{total}\nOH {on_hold / total:.0%} | NR {not_reportable / total:.0%}"
                        )
                        tooltip = (
                            f"Total tests: {total}\n"
                            f"ON HOLD: {on_hold} ({float(point.get('on_hold_ratio') or 0.0):.1%})\n"
                            f"NOT REPORTABLE: {not_reportable} ({float(point.get('not_reportable_ratio') or 0.0):.1%})\n"
                            f"Beyond SLA: {beyond_sla} ({float(point.get('sla_breach_ratio') or 0.0):.1%})"
                        )
                        item.setToolTip(tooltip)
                    color = _ratio_color(max_ratio)
                    item.setBackground(QtGui.QBrush(color))
                self.table.setItem(row_index, col_index, item)

        self.table.resizeColumnsToContents()
        if self.table.horizontalHeader().sectionSize(0) > 220:
            self.table.horizontalHeader().resizeSection(0, 220)


STATE_COLORS = {
    "ON HOLD": "#F85149",
    "NOT REPORTABLE": "#FF9B44",
    "IN PROGRESS": "#4C6EF5",
    "NOT STARTED": "#8D96B4",
    "COMPLETED": "#7EE787",
    "REPORTED": "#2EA043",
    "CANCELLED": "#9E9E9E",
    "CLIENT CANCELLED": "#BC8CFF",
    "UNKNOWN": "#6E7681",
}


class TestsStateStackedBarChart(ChartCard):
    """Stacked bar chart displaying tests by state over time."""

    def __init__(self, title: str = "Tests by State", parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(title, parent)
        self.chart.removeAllSeries()

        self.series = QtCharts.QStackedBarSeries()
        self.series.setBarWidth(0.6)
        self.chart.addSeries(self.series)

        self.categories_axis = QtCharts.QBarCategoryAxis()
        self.categories_axis.setLabelsColor(QtGui.QColor("white"))
        self.categories_axis.setTitleText("Periodo")
        self.chart.addAxis(self.categories_axis, QtCore.Qt.AlignmentFlag.AlignBottom)
        self.series.attachAxis(self.categories_axis)

        self.value_axis = QtCharts.QValueAxis()
        self.value_axis.setLabelFormat("%d")
        self.value_axis.setTitleText("Tests")
        self.value_axis.setLabelsColor(QtGui.QColor("white"))
        self.value_axis.setTitleBrush(QtGui.QBrush(QtGui.QColor("white")))
        self.chart.addAxis(self.value_axis, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.value_axis)

    def update_data(self, series_points: Sequence[dict], states: Sequence[str]) -> None:
        self.chart.removeSeries(self.series)
        self.series = QtCharts.QStackedBarSeries()
        self.series.setBarWidth(0.6)

        state_order = list(states)
        categories: list[str] = []
        max_total = 0

        bar_sets: dict[str, QtCharts.QBarSet] = {}
        for state in state_order:
            bar_set = QtCharts.QBarSet(state)
            color = QtGui.QColor(STATE_COLORS.get(state, "#6E7681"))
            bar_set.setColor(color)
            bar_set.setBorderColor(color.darker(125))
            bar_sets[state] = bar_set
            self.series.append(bar_set)

        for point in series_points:
            period = point.get("period_start")
            label = period.strftime("%Y-%m-%d") if isinstance(period, date) else str(period)
            categories.append(label)
            buckets = {bucket["state"]: int(bucket.get("count", 0)) for bucket in point.get("buckets", [])}
            total = 0
            for state in state_order:
                value = buckets.get(state, 0)
                bar_sets[state].append(value)
                total += value
            max_total = max(max_total, total)

        self.chart.addSeries(self.series)
        self.series.attachAxis(self.categories_axis)
        self.series.attachAxis(self.value_axis)

        self.categories_axis.clear()
        self.categories_axis.append(categories)
        self.value_axis.setRange(0, max_total * 1.2 if max_total else 1)
