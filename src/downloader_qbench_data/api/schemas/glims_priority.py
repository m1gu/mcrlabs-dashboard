from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class PriorityTestItem(BaseModel):
    label: str
    start_date: Optional[date] = None
    complete: bool
    status: Optional[str] = None


class PrioritySampleItem(BaseModel):
    sample_id: str
    client_name: Optional[str] = None
    dispensary_id: Optional[int] = None
    dispensary_name: Optional[str] = None
    date_received: Optional[date] = None
    report_date: Optional[date] = None
    open_hours: Optional[float] = None
    tests_total: int
    tests_complete: int
    tests: List[PriorityTestItem]
    status: Optional[str] = None


class PrioritySampleResponse(BaseModel):
    samples: List[PrioritySampleItem]


class PriorityHeatmapItem(BaseModel):
    dispensary_id: Optional[int] = None
    dispensary_name: Optional[str] = None
    period_start: date
    count: int


class PriorityHeatmapResponse(BaseModel):
    buckets: List[PriorityHeatmapItem]
