from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from downloader_qbench_data.api.dependencies import get_db_session, require_active_user
from downloader_qbench_data.api.schemas.glims_tests import (
    TestsSummary,
    TestsActivityPoint,
    TestsActivityResponse,
    TestsTrendPoint,
    TestsTrendResponse,
)

router = APIRouter(
    prefix="/api/v2/glims/tests",
    tags=["glims-tests"],
    dependencies=[Depends(require_active_user)],
)

# Same mapping as overview to ensure consistency
ASSAY_TABLES = {
    "CN": ("glims_cn_results", "prep_date", "start_date"),
    "TP": ("glims_tp_results", "prep_date", "start_date"),
    "PS": ("glims_ps_results", "prep_date", "start_date"),
    "HM": ("glims_hm_results", "prep_date", "start_date"),
    "RS": ("glims_rs_results", "prep_date", "start_date"),
    "MY": ("glims_my_results", "prep_date", "start_date"),
    "MB": ("glims_mb_results", "tempo_prep_date", "GREATEST(ac_cc_eb_read_date, ym_read_date, sal_read_date, stec_read_date)"),
    "WA": ("glims_wa_results", "prep_date", "start_date"),
    "MC": ("glims_mc_results", "prep_date", "start_date"),
    "PN": ("glims_pn_results", "prep_date", "start_date"),
    "FFM": ("glims_ffm_results", "analysis_date", "analysis_date"),
    "LW": ("glims_lw_results", "run_date", "run_date"),
    "HO": ("glims_ho_results", "prep_date", "start_date"),
}

def _parse_dates(date_from: Optional[date], date_to: Optional[date]) -> tuple[date, date]:
    if not date_to:
        date_to = date.today()
    if not date_from:
        date_from = date_to - timedelta(days=7)
    return date_from, date_to

@router.get("/summary", response_model=TestsSummary)
def get_summary(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    session: Session = Depends(get_db_session),
) -> TestsSummary:
    start, end = _parse_dates(date_from, date_to)
    
    unions = []
    for label, (table, p_date, s_date) in ASSAY_TABLES.items():
        unions.append(f"""
            SELECT 
                '{label}' as type,
                EXTRACT(EPOCH FROM ({s_date}::timestamp - {p_date}::timestamp))/3600.0 as diff_hours
            FROM {table}
            WHERE {p_date} BETWEEN :start AND :end OR {s_date} BETWEEN :start AND :end
        """)
    
    sql = f"""
        WITH all_tests AS (
            {" UNION ALL ".join(unions)}
        )
        SELECT 
            type,
            COUNT(*) as total,
            AVG(diff_hours) FILTER (WHERE diff_hours >= 0) as avg_diff
        FROM all_tests
        GROUP BY type
    """
    
    rows = session.execute(text(sql), {"start": start, "end": end}).all()
    
    tests_by_type = {}
    avg_by_type = {}
    total_tests = 0
    total_weighted_hours = 0.0
    total_count_for_avg = 0
    
    for row in rows:
        count = row.total or 0
        avg_h = float(row.avg_diff) if row.avg_diff is not None else None
        
        tests_by_type[row.type] = count
        total_tests += count
        
        if avg_h is not None:
            avg_by_type[row.type] = avg_h
            total_weighted_hours += avg_h * count
            total_count_for_avg += count
            
    avg_global = total_weighted_hours / total_count_for_avg if total_count_for_avg > 0 else None
    
    return TestsSummary(
        total_tests=total_tests,
        avg_prep_to_start_hours=avg_global,
        tests_by_type=tests_by_type,
        avg_by_type=avg_by_type
    )

@router.get("/activity", response_model=TestsActivityResponse)
def get_activity(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    session: Session = Depends(get_db_session),
) -> TestsActivityResponse:
    start, end = _parse_dates(date_from, date_to)
    
    prep_unions = []
    start_unions = []
    
    for label, (table, p_date, s_date) in ASSAY_TABLES.items():
        prep_unions.append(f"SELECT '{label}' as type, 'prep' as category, {p_date}::date as d FROM {table} WHERE {p_date} BETWEEN :start AND :end")
        start_unions.append(f"SELECT '{label}' as type, 'start' as category, {s_date}::date as d FROM {table} WHERE {s_date} BETWEEN :start AND :end")
        
    sql = f"""
        WITH all_activity AS (
            {" UNION ALL ".join(prep_unions)}
            UNION ALL
            {" UNION ALL ".join(start_unions)}
        )
        SELECT 
            d,
            category,
            type,
            COUNT(*) as count
        FROM all_activity
        GROUP BY d, category, type
        ORDER BY d
    """
    
    rows = session.execute(text(sql), {"start": start, "end": end}).all()
    
    points_map: dict[date, TestsActivityPoint] = {}
    for row in rows:
        if row.d not in points_map:
            points_map[row.d] = TestsActivityPoint(date=row.d)
        
        p = points_map[row.d]
        count = row.count or 0
        if row.category == 'prep':
            p.prep_breakdown[row.type] = p.prep_breakdown.get(row.type, 0) + count
            p.total_prep += count
        else:
            p.start_breakdown[row.type] = p.start_breakdown.get(row.type, 0) + count
            p.total_start += count
            
    return TestsActivityResponse(points=sorted(points_map.values(), key=lambda x: x.date))

@router.get("/trend", response_model=TestsTrendResponse)
def get_trend(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    moving_avg_window: int = Query(7, ge=1, le=30),
    session: Session = Depends(get_db_session),
) -> TestsTrendResponse:
    start, end = _parse_dates(date_from, date_to)
    
    unions = []
    for label, (table, p_date, s_date) in ASSAY_TABLES.items():
        unions.append(f"""
            SELECT 
                {s_date}::date as d,
                EXTRACT(EPOCH FROM ({s_date}::timestamp - {p_date}::timestamp))/3600.0 as diff_hours
            FROM {table}
            WHERE {s_date} BETWEEN :start AND :end
        """)
        
    sql = f"""
        WITH daily_diffs AS (
            {" UNION ALL ".join(unions)}
        )
        SELECT 
            d,
            AVG(diff_hours) FILTER (WHERE diff_hours >= 0) as avg_hours
        FROM daily_diffs
        GROUP BY d
        ORDER BY d
    """
    
    rows = session.execute(text(sql), {"start": start, "end": end}).all()
    points = [TestsTrendPoint(date=row.d, avg_hours=float(row.avg_hours) if row.avg_hours is not None else None) for row in rows]
    
    # Calculate moving average
    for idx, point in enumerate(points):
        window_start = max(0, idx - moving_avg_window + 1)
        window = points[window_start : idx + 1]
        values = [p.avg_hours for p in window if p.avg_hours is not None]
        if values:
            point.moving_avg_hours = sum(values) / len(values)
            
    return TestsTrendResponse(points=points)
