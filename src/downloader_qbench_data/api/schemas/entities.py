"""Pydantic schemas for entity detail endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OrderSampleTestItem(BaseModel):
    id: int
    label_abbr: Optional[str] = None
    state: Optional[str] = None
    has_report: bool = False
    report_completed_date: Optional[datetime] = None


class OrderSampleItem(BaseModel):
    id: int
    sample_name: Optional[str] = None
    state: Optional[str] = None
    has_report: bool = False
    pending_tests: Optional[int] = None
    tests: Optional[list[OrderSampleTestItem]] = None


class OrderDetailResponse(BaseModel):
    order: dict
    customer: Optional[dict] = None
    samples: Optional[list[OrderSampleItem]] = None


class SampleTestItem(BaseModel):
    id: int
    label_abbr: Optional[str] = None
    state: Optional[str] = None
    has_report: bool = False
    report_completed_date: Optional[datetime] = None


class SampleBatchItem(BaseModel):
    id: int
    display_name: Optional[str] = None


class SampleDetailResponse(BaseModel):
    sample: dict
    order: Optional[dict] = None
    tests: Optional[list[SampleTestItem]] = None
    batches: Optional[list[SampleBatchItem]] = None


class TestBatchItem(BaseModel):
    id: int
    display_name: Optional[str] = Field(None, description="User-friendly batch name")


class TestDetailResponse(BaseModel):
    test: dict
    sample: Optional[dict] = None
    order: Optional[dict] = None
    batches: Optional[list[TestBatchItem]] = None
