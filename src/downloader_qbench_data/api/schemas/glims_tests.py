from __future__ import annotations
from datetime import date
from typing import Optional, Dict
from pydantic import BaseModel

class TestsSummary(BaseModel):
    total_tests: int
    avg_prep_to_start_hours: Optional[float] = None
    tests_by_type: Dict[str, int] = {}
    avg_by_type: Dict[str, float] = {}

class TestsActivityPoint(BaseModel):
    date: date
    prep_breakdown: Dict[str, int] = {}
    start_breakdown: Dict[str, int] = {}
    total_prep: int = 0
    total_start: int = 0

class TestsActivityResponse(BaseModel):
    points: list[TestsActivityPoint]

class TestsTrendPoint(BaseModel):
    date: date
    avg_hours: Optional[float] = None
    moving_avg_hours: Optional[float] = None

class TestsTrendResponse(BaseModel):
    points: list[TestsTrendPoint]
