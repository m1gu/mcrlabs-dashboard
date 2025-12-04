"""HTTP client used by the dashboard to gather metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

import httpx


def _parse_date(value: str | None) -> Optional[date]:
    if not value:
        return None
    return datetime.fromisoformat(value).date()


def _parse_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class ApiClient:
    """Thin synchronous client for dashboard endpoints."""

    def __init__(self, base_url: str = "http://localhost:8000/api/v1", timeout: float = 30.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._client.close()

    # Summary -----------------------------------------------------------------

    def fetch_summary(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        customer_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        params = {}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        if customer_id:
            params["customer_id"] = customer_id
        response = self._client.get("/metrics/summary", params=params)
        response.raise_for_status()
        payload = response.json()
        payload["last_updated_at"] = _parse_datetime(payload.get("last_updated_at"))
        payload["range_start"] = _parse_datetime(payload.get("range_start"))
        payload["range_end"] = _parse_datetime(payload.get("range_end"))
        return payload

    # Activity ----------------------------------------------------------------

    def fetch_daily_activity(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        compare_previous: bool = False,
    ) -> Dict[str, Dict[date, int]]:
        params = {"compare_previous": "true" if compare_previous else "false"}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        response = self._client.get("/metrics/activity/daily", params=params)
        response.raise_for_status()
        data = response.json()

        current_samples: Dict[date, int] = {}
        current_tests: Dict[date, int] = {}
        for item in data.get("current", []):
            day = _parse_date(item.get("date"))
            if not day:
                continue
            current_samples[day] = int(item.get("samples") or 0)
            current_tests[day] = int(item.get("tests") or 0)

        previous_samples: Dict[date, int] = {}
        previous_tests: Dict[date, int] = {}
        for item in data.get("previous") or []:
            day = _parse_date(item.get("date"))
            if not day:
                continue
            previous_samples[day] = int(item.get("samples") or 0)
            previous_tests[day] = int(item.get("tests") or 0)

        return {
            "current_samples": current_samples,
            "current_tests": current_tests,
            "previous_samples": previous_samples,
            "previous_tests": previous_tests,
        }

    # Customers ---------------------------------------------------------------

    def fetch_new_customers(
        self, *, date_from: Optional[date] = None, date_to: Optional[date] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        params = {"limit": limit}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        response = self._client.get("/metrics/customers/new", params=params)
        response.raise_for_status()

        customers = []
        for item in response.json().get("customers", []):
            item["created_at"] = _parse_datetime(item.get("created_at"))
            customers.append(item)
        return customers

    def fetch_top_customers(self, *, date_from: Optional[date] = None, date_to: Optional[date] = None, limit: int = 10) -> List[Dict[str, Any]]:
        params = {"limit": limit}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        response = self._client.get("/metrics/customers/top-tests", params=params)
        response.raise_for_status()
        return response.json().get("customers", [])

    # Reports -----------------------------------------------------------------

    def fetch_reports_overview(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        response = self._client.get("/metrics/reports/overview", params=params)
        response.raise_for_status()
        return response.json()

    # TAT ---------------------------------------------------------------------

    def fetch_tat_daily(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        moving_average_window: int = 7,
    ) -> Dict[str, Any]:
        params = {"moving_average_window": moving_average_window}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        response = self._client.get("/metrics/tests/tat-daily", params=params)
        response.raise_for_status()
        payload = response.json()
        payload["points"] = [
            {
                "date": _parse_date(item.get("date")),
                "average_hours": item.get("average_hours"),
                "within_sla": item.get("within_sla", 0),
                "beyond_sla": item.get("beyond_sla", 0),
            }
            for item in payload.get("points", [])
            if _parse_date(item.get("date"))
        ]
        payload["moving_average_hours"] = [
            {
                "period_start": _parse_date(item.get("period_start")),
                "value": item.get("value"),
            }
            for item in payload.get("moving_average_hours") or []
            if _parse_date(item.get("period_start"))
        ]
        return payload

    # Quality & SLA ----------------------------------------------------------

    def fetch_customer_alerts(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        customer_id: Optional[int] = None,
        interval: str = "week",
        sla_hours: float = 48.0,
        min_alert_percentage: float = 0.1,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "interval": interval,
            "sla_hours": sla_hours,
            "min_alert_percentage": min_alert_percentage,
        }
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        if customer_id:
            params["customer_id"] = customer_id
        response = self._client.get("/analytics/customers/alerts", params=params)
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("heatmap", []):
            item["period_start"] = _parse_date(item.get("period_start"))
        for alert in payload.get("alerts", []):
            alert["latest_activity_at"] = _parse_datetime(alert.get("latest_activity_at"))
        return payload

    def fetch_tests_state_distribution(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        customer_id: Optional[int] = None,
        order_id: Optional[int] = None,
        interval: str = "week",
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"interval": interval}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        if customer_id:
            params["customer_id"] = customer_id
        if order_id:
            params["order_id"] = order_id
        response = self._client.get("/analytics/tests/state-distribution", params=params)
        response.raise_for_status()
        payload = response.json()
        for point in payload.get("series", []):
            point["period_start"] = _parse_date(point.get("period_start"))
        return payload

    def fetch_quality_kpis(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        customer_id: Optional[int] = None,
        order_id: Optional[int] = None,
        sla_hours: float = 48.0,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"sla_hours": sla_hours}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        if customer_id:
            params["customer_id"] = customer_id
        if order_id:
            params["order_id"] = order_id
        response = self._client.get("/analytics/kpis/quality", params=params)
        response.raise_for_status()
        return response.json()

    # Activity chart expects raw counts from current/previous; helper methods above cover.
