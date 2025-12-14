from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from downloader_qbench_data.api import create_app
from downloader_qbench_data.api.dependencies import get_db_session, require_active_user


class _FakeResultStats:
    def one(self):
        return SimpleNamespace(total=2, avg_open=84.0, p95_open=120.0)


class _FakeResultData:
    def all(self):
        return [
            SimpleNamespace(
                sample_id="S2",
                dispensary_id=1,
                dispensary_name="Alpha Labs",
                date_received="2025-01-02",
                report_date="2025-01-06",
                tests_count=2,
                open_hours=96.0,
            ),
            SimpleNamespace(
                sample_id="S1",
                dispensary_id=1,
                dispensary_name="Alpha Labs",
                date_received="2025-01-01",
                report_date="2025-01-04",
                tests_count=1,
                open_hours=72.0,
            ),
        ]


class _FakeSession:
    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "PERCENTILE_CONT" in sql:
            return _FakeResultStats()
        return _FakeResultData()


def create_test_client():
    app = create_app()

    def _dummy_session():
        yield _FakeSession()

    app.dependency_overrides[get_db_session] = _dummy_session
    app.dependency_overrides[require_active_user] = lambda: SimpleNamespace(username="tester")
    return TestClient(app)


def test_glims_tat_slowest_endpoint_returns_items_and_stats():
    client = create_test_client()
    resp = client.get("/api/v2/glims/tat/slowest?min_open_hours=70&outlier_threshold_hours=90")
    assert resp.status_code == 200
    body = resp.json()

    assert body["stats"]["total_samples"] == 2
    assert body["stats"]["average_open_hours"] == 84.0
    assert body["stats"]["percentile_95_open_hours"] == 120.0
    assert body["stats"]["threshold_hours"] == 90.0

    items = body["items"]
    assert len(items) == 2
    # Ordered by open_hours desc
    assert items[0]["sample_id"] == "S2"
    assert items[0]["tests_count"] == 2
    assert items[0]["is_outlier"] is True  # 96 >= 90
    assert items[1]["is_outlier"] is False  # 72 < 90
