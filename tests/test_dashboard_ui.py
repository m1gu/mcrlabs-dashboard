from __future__ import annotations

import sys
from datetime import date, datetime

import pytest
from PySide6.QtWidgets import QApplication
from PySide6 import QtTest

from downloader_qbench_data.ui.dashboard import DashboardConfig, DashboardWindow


class DummyApiClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def fetch_summary(self, **kwargs):
        return {
            'kpis': {
                'total_samples': 200,
                'total_tests': 400,
                'total_customers': 12,
                'total_reports': 55,
                'average_tat_hours': 36.5,
            },
            'last_updated_at': datetime(2025, 10, 17, 12, 30),
            'range_start': datetime(2025, 10, 10),
            'range_end': datetime(2025, 10, 17),
        }

    def fetch_daily_activity(self, **kwargs):
        return {
            'current_samples': {date(2025, 10, 15): 20, date(2025, 10, 16): 25},
            'current_tests': {date(2025, 10, 15): 40, date(2025, 10, 16): 50},
            'previous_samples': {},
            'previous_tests': {},
        }

    def fetch_new_customers(self, **kwargs):
        return [
            {'id': 1, 'name': 'Acme', 'created_at': datetime(2025, 10, 16)},
            {'id': 2, 'name': 'Globex', 'created_at': datetime(2025, 10, 15)},
        ]

    def fetch_top_customers(self, **kwargs):
        return [
            {'id': 1, 'name': 'Acme', 'tests': 50},
            {'id': 2, 'name': 'Globex', 'tests': 30},
        ]

    def fetch_reports_overview(self, **kwargs):
        return {'total_reports': 55, 'reports_within_sla': 40, 'reports_beyond_sla': 15}

    def fetch_tat_daily(self, **kwargs):
        return {
            'points': [
                {'date': date(2025, 10, 15), 'average_hours': 40, 'within_sla': 30, 'beyond_sla': 5},
                {'date': date(2025, 10, 16), 'average_hours': 42, 'within_sla': 28, 'beyond_sla': 6},
            ],
            'moving_average_hours': [
                {'period_start': date(2025, 10, 16), 'value': 41.0},
            ],
        }


@pytest.fixture(scope='module')
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_dashboard_window_initialises(qt_app):
    client = DummyApiClient()
    window = DashboardWindow(api_client=client, config=DashboardConfig())
    window.show()
    qt_app.processEvents()
    for _ in range(5):
        qt_app.processEvents()
        QtTest.QTest.qWait(100)
    assert window.samples_card.value_label.text() != '--'
    assert window.tests_card.value_label.text() != '--'
    window.close()
    assert client.closed

