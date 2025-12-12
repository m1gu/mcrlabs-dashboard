"""Pydantic schemas for GLIMS overview endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class OverviewSummary(BaseModel):
    samples: int
    tests: int
    customers: int
    reports: int
    avg_tat_hours: Optional[float] = None
    last_sync_at: Optional[datetime] = Field(
        None,
        description="Timestamp of the latest successful GLIMS sync run.",
    )
    last_updated_at: Optional[date] = Field(
        None,
        description="Latest date seen in the dataset for the requested range.",
    )


class ActivityPoint(BaseModel):
    date: date
    samples: int
    tests: int
    samples_reported: int


class ActivityResponse(BaseModel):
    points: List[ActivityPoint]


class NewCustomerItem(BaseModel):
    id: int
    name: str
    created_at: date


class NewCustomersResponse(BaseModel):
    customers: List[NewCustomerItem]


class TopCustomerItem(BaseModel):
    id: int
    name: str
    tests: int
    tests_reported: int


class TopCustomersResponse(BaseModel):
    customers: List[TopCustomerItem]


class TestsByLabelItem(BaseModel):
    key: str
    count: int


class TestsByLabelResponse(BaseModel):
    labels: List[TestsByLabelItem]


class TatDailyPoint(BaseModel):
    date: date
    average_hours: Optional[float] = None
    within_tat: int
    beyond_tat: int
    moving_average_hours: Optional[float] = None


class TatDailyResponse(BaseModel):
    points: List[TatDailyPoint]
