from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class GlimsTatStats(BaseModel):
    total_samples: int = Field(..., description="Samples included in the filtered window")
    average_open_hours: Optional[float] = Field(None, description="Average hours between received and reported")
    percentile_95_open_hours: Optional[float] = Field(None, description="95th percentile of open hours")
    threshold_hours: Optional[float] = Field(None, description="Threshold used to flag outliers")


class GlimsTatItem(BaseModel):
    sample_id: str = Field(..., description="GLIMS sample identifier")
    dispensary_id: Optional[int] = Field(None, description="Linked dispensary identifier")
    dispensary_name: Optional[str] = Field(None, description="Linked dispensary name")
    date_received: Optional[date] = Field(None, description="Sample received date")
    report_date: Optional[date] = Field(None, description="Sample report date")
    tests_count: int = Field(..., description="Number of assays with results for the sample")
    open_time_hours: float = Field(..., description="Hours between received and reported")
    open_time_label: str = Field(..., description="Human-readable open time (e.g. '3d 4h')")
    is_outlier: bool = Field(False, description="Whether the sample exceeds the configured threshold")


class GlimsTatResponse(BaseModel):
    stats: GlimsTatStats
    items: list[GlimsTatItem]
