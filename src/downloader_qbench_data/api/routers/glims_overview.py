"""API v2 GLIMS overview endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from downloader_qbench_data.api.dependencies import get_db_session, get_app_settings, require_active_user
from downloader_qbench_data.config import AppSettings
from downloader_qbench_data.api.schemas.glims_overview import (
    ActivityPoint,
    ActivityResponse,
    NewCustomerItem,
    NewCustomersResponse,
    OverviewSummary,
    TatDailyPoint,
    TatDailyResponse,
    TestsByLabelItem,
    TestsByLabelResponse,
    TopCustomerItem,
    TopCustomersResponse,
    NewCustomerFromSheetItem,
    NewCustomersFromSheetResponse,
)

router = APIRouter(
    prefix="/api/v2/glims/overview",
    tags=["glims-overview"],
    dependencies=[Depends(require_active_user)],
)

ASSAY_TABLES = {
    "CN": ("glims_cn_results", "prep_date", "start_date"),
    "TP": ("glims_tp_results", "prep_date", "start_date"),
    "PS": ("glims_ps_results", "prep_date", "start_date"),
    "HM": ("glims_hm_results", "prep_date", "start_date"),
    "RS": ("glims_rs_results", "prep_date", "start_date"),
    "MY": ("glims_my_results", "prep_date", "start_date"),
    "MB": ("glims_mb_results", "tempo_prep_date", "ac_cc_eb_read_date"),
    "WA": ("glims_wa_results", "prep_date", "start_date"),
    "MC": ("glims_mc_results", "prep_date", "start_date"),
    "PN": ("glims_pn_results", "prep_date", "start_date"),
    "FFM": ("glims_ffm_results", "analysis_date", "analysis_date"),
    "LW": ("glims_lw_results", "run_date", "run_date"),
    "HO": ("glims_ho_results", "prep_date", "start_date"),
}


def _parse_dates(
    date_from: Optional[date],
    date_to: Optional[date],
    default_days: int = 7,
) -> tuple[date, date]:
    today = datetime.utcnow().date()
    if date_from is None and date_to is None:
        date_to = today
        date_from = today - timedelta(days=default_days - 1)
    elif date_from is None:
        date_from = date_to - timedelta(days=default_days - 1)
    elif date_to is None:
        date_to = date_from + timedelta(days=default_days - 1)

    if date_from > date_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date_from_must_be_before_date_to")
    return date_from, date_to


@router.get("/summary", response_model=OverviewSummary)
def get_summary(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    dispensary_id: Optional[int] = Query(None),
    sample_type: Optional[str] = Query(None),
    settings: AppSettings = Depends(get_app_settings),
    session: Session = Depends(get_db_session),
) -> OverviewSummary:
    start, end = _parse_dates(date_from, date_to)

    filters = ["s.date_received BETWEEN :start AND :end"]
    params = {"start": start, "end": end}
    if dispensary_id:
        filters.append("s.dispensary_id = :dispensary_id")
        params["dispensary_id"] = dispensary_id
    if sample_type and sample_type != 'All':
        filters.append("s.adult_use_medical = :sample_type")
        params["sample_type"] = sample_type
    
    filters.append("s.status NOT IN ('Cancelled', 'Destroyed')")
    # Query 1: Intake Metrics (based on date_received)
    intake_where = " AND ".join(filters) # Already defined as date_received filter
    
    # Query 1: Intake Metrics (based on date_received)
    intake_sql = f"""
        SELECT
            COUNT(*) AS samples,
            adult_use_medical,
            MAX(GREATEST(s.date_received, s.report_date)) AS last_updated_at
        FROM glims_samples s
        WHERE {intake_where}
        GROUP BY adult_use_medical
    """
    samples_total = 0
    samples_by_type = {}
    last_updated_at = None
    for row in session.execute(text(intake_sql), params):
        samples_total += row.samples
        samples_by_type[row.adult_use_medical or "Unknown"] = row.samples
        if row.last_updated_at:
            if last_updated_at is None or row.last_updated_at > last_updated_at:
                last_updated_at = row.last_updated_at

    # Query New Customers from the dedicated table
    new_customers_sql = """
        SELECT COUNT(*)
        FROM glims_new_customers
        WHERE date_created BETWEEN :start AND :end
    """
    new_customers_params = {"start": start, "end": end}
    
    if dispensary_id:
        disp_name = session.execute(
            text("SELECT name FROM glims_dispensaries WHERE id = :id"),
            {"id": dispensary_id}
        ).scalar()
        if disp_name:
            new_customers_sql += " AND client_name = :name"
            new_customers_params["name"] = disp_name
        else:
            new_customers_sql += " AND 1=0"

    new_customers_count = session.execute(text(new_customers_sql), new_customers_params).scalar() or 0

    # Query 2: Output Metrics (based on report_date)
    output_filters = ["s.report_date BETWEEN :start AND :end"]
    if dispensary_id:
        output_filters.append("s.dispensary_id = :dispensary_id")
    if sample_type and sample_type != 'All':
        output_filters.append("s.adult_use_medical = :sample_type")
    output_where = " AND ".join(output_filters)

    output_sql = f"""
        SELECT
            COUNT(*) AS reports,
            adult_use_medical,
            AVG(EXTRACT(EPOCH FROM (s.report_date::timestamp - s.date_received::timestamp))/3600.0) AS avg_tat_hours
        FROM glims_samples s
        WHERE {output_where}
        GROUP BY adult_use_medical
    """
    reports_total = 0
    reports_by_type = {}
    tat_by_type = {}
    total_tat_hours = 0.0
    tat_count = 0
    for row in session.execute(text(output_sql), params):
        reports_total += row.reports
        type_key = row.adult_use_medical or "Unknown"
        reports_by_type[type_key] = row.reports
        if row.avg_tat_hours is not None:
            tat_by_type[type_key] = float(row.avg_tat_hours)
            total_tat_hours += float(row.avg_tat_hours) * row.reports
            tat_count += row.reports

    sync_sql = """
        SELECT finished_at
        FROM glims_sync_runs
        WHERE status = 'success'
        ORDER BY finished_at DESC
        LIMIT 1
    """
    last_sync_at = session.execute(text(sync_sql)).scalar_one_or_none()

    tests_total = 0
    tests_by_type = {}
    for label, (table, date_a, date_b) in ASSAY_TABLES.items():
        test_sql = f"""
            SELECT COUNT(*) AS c, s.adult_use_medical
            FROM {table} r
            JOIN glims_samples s ON s.sample_id = r.sample_id
            WHERE COALESCE(r.{date_a}, r.{date_b}, s.date_received) BETWEEN :start AND :end
            {"AND s.dispensary_id = :dispensary_id" if dispensary_id else ""}
            {"AND s.adult_use_medical = :sample_type" if sample_type and sample_type != 'All' else ""}
            GROUP BY s.adult_use_medical
        """
        for row in session.execute(text(test_sql), params):
            tests_total += row.c
            cat = row.adult_use_medical or "Unknown"
            tests_by_type[cat] = tests_by_type.get(cat, 0) + row.c

    return OverviewSummary(
        samples=samples_total,
        tests=tests_total,
        customers=new_customers_count,
        reports=reports_total,
        avg_tat_hours=total_tat_hours / tat_count if tat_count > 0 else None,
        samples_by_type=samples_by_type,
        tests_by_type=tests_by_type,
        reports_by_type=reports_by_type,
        tat_by_type=tat_by_type,
        last_sync_at=last_sync_at,
        last_updated_at=last_updated_at,
    )


@router.get("/activity", response_model=ActivityResponse)
def get_activity(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    dispensary_id: Optional[int] = Query(None),
    sample_type: Optional[str] = Query(None),
    session: Session = Depends(get_db_session),
) -> ActivityResponse:
    start, end = _parse_dates(date_from, date_to)
    params = {"start": start, "end": end}
    samples_where = ["s.date_received BETWEEN :start AND :end"]
    if dispensary_id:
        samples_where.append("s.dispensary_id = :dispensary_id")
    if sample_type and sample_type != 'All':
        samples_where.append("s.adult_use_medical = :sample_type")
        params["sample_type"] = sample_type

    samples_sql = f"""
        SELECT s.date_received AS d, s.adult_use_medical, COUNT(*) AS c
        FROM glims_samples s
        WHERE {" AND ".join(samples_where)}
        GROUP BY s.date_received, s.adult_use_medical
    """
    
    samples_map: dict[date, int] = {}
    breakdown_map: dict[date, dict[str, int]] = {}

    for row in session.execute(text(samples_sql), params):
        d_val = row.d
        category = row.adult_use_medical or "Unknown"
        count = row.c
        
        samples_map[d_val] = samples_map.get(d_val, 0) + count
        
        if d_val not in breakdown_map:
            breakdown_map[d_val] = {}
        breakdown_map[d_val][category] = breakdown_map[d_val].get(category, 0) + count

    disp_clause = "AND s.dispensary_id = :dispensary_id" if dispensary_id else ""
    type_clause = "AND s.adult_use_medical = :sample_type" if sample_type and sample_type != 'All' else ""

    reported_sql = f"""
        SELECT s.report_date AS d, s.adult_use_medical, COUNT(*) AS c
        FROM glims_samples s
        WHERE s.report_date BETWEEN :start AND :end {disp_clause} {type_clause}
        GROUP BY s.report_date, s.adult_use_medical
    """
    reported_map: dict[date, int] = {}
    reported_breakdown: dict[date, dict[str, int]] = {}
    for row in session.execute(text(reported_sql), params):
        d_val = row.d
        cat = row.adult_use_medical or "Unknown"
        reported_map[d_val] = reported_map.get(d_val, 0) + row.c
        if d_val not in reported_breakdown:
            reported_breakdown[d_val] = {}
        reported_breakdown[d_val][cat] = row.c

    tests_map: dict[date, int] = {}
    tests_breakdown: dict[date, dict[str, int]] = {}
    for label, (table, date_a, date_b) in ASSAY_TABLES.items():
        test_sql = f"""
            SELECT COALESCE(r.{date_a}, r.{date_b}, s.date_received) AS d, s.adult_use_medical, COUNT(*) AS c
            FROM {table} r
            JOIN glims_samples s ON s.sample_id = r.sample_id
            WHERE COALESCE(r.{date_a}, r.{date_b}, s.date_received) BETWEEN :start AND :end 
            {disp_clause} {type_clause}
            GROUP BY COALESCE(r.{date_a}, r.{date_b}, s.date_received), s.adult_use_medical
        """
        for row in session.execute(text(test_sql), params):
            d_val = row.d
            cat = row.adult_use_medical or "Unknown"
            tests_map[d_val] = tests_map.get(d_val, 0) + row.c
            if d_val not in tests_breakdown:
                tests_breakdown[d_val] = {}
            tests_breakdown[d_val][cat] = tests_breakdown[d_val].get(cat, 0) + row.c

    points: list[ActivityPoint] = []
    current = start
    while current <= end:
        points.append(
            ActivityPoint(
                date=current,
                samples=samples_map.get(current, 0),
                tests=tests_map.get(current, 0),
                samples_reported=reported_map.get(current, 0),
                samples_breakdown=breakdown_map.get(current, {}),
                tests_breakdown=tests_breakdown.get(current, {}),
                reported_breakdown=reported_breakdown.get(current, {}),
            )
        )
        current += timedelta(days=1)
    return ActivityResponse(points=points)


@router.get("/customers/new", response_model=NewCustomersResponse)
def get_new_customers(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_db_session),
) -> NewCustomersResponse:
    start, end = _parse_dates(date_from, date_to)
    sql = """
        SELECT d.id, d.name, MIN(s.date_received) AS created_at
        FROM glims_samples s
        JOIN glims_dispensaries d ON d.id = s.dispensary_id
        WHERE s.date_received BETWEEN :start AND :end
        GROUP BY d.id, d.name
        ORDER BY created_at DESC
        LIMIT :limit
    """
    rows = session.execute(text(sql), {"start": start, "end": end, "limit": limit}).all()
    customers = [NewCustomerItem(id=row.id, name=row.name, created_at=row.created_at) for row in rows]
    return NewCustomersResponse(customers=customers)


@router.get("/customers/new-from-sheet", response_model=NewCustomersFromSheetResponse)
def get_new_customers_from_sheet(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_db_session),
) -> NewCustomersFromSheetResponse:
    """
    Retorna los nuevos customers detectados desde el tab Dispensaries del Google Sheet.
    Usa la tabla glims_new_customers.
    """
    start, end = _parse_dates(date_from, date_to)

    sql = """
        SELECT client_id, client_name, date_created
        FROM glims_new_customers
        WHERE date_created BETWEEN :start AND :end
        ORDER BY client_id DESC
        LIMIT :limit
    """
    rows = session.execute(text(sql), {"start": start, "end": end, "limit": limit}).all()

    count_sql = """
        SELECT COUNT(*) FROM glims_new_customers
        WHERE date_created BETWEEN :start AND :end
    """
    total = session.execute(text(count_sql), {"start": start, "end": end}).scalar_one()

    customers = [
        NewCustomerFromSheetItem(
            client_id=row.client_id,
            client_name=row.client_name,
            date_created=row.date_created,
        )
        for row in rows
    ]
    return NewCustomersFromSheetResponse(customers=customers, total=total)


@router.get("/customers/top-tests", response_model=TopCustomersResponse)
def get_top_customers(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_db_session),
) -> TopCustomersResponse:
    start, end = _parse_dates(date_from, date_to)
    params = {"start": start, "end": end, "limit": limit}

    test_union_parts = []
    for label, (table, date_a, date_b) in ASSAY_TABLES.items():
        test_union_parts.append(
            f"SELECT r.sample_id, COALESCE(r.{date_a}, r.{date_b}, s.date_received) AS d FROM {table} r JOIN glims_samples s ON s.sample_id = r.sample_id"
        )
    test_union = " UNION ALL ".join(test_union_parts)
    sql = f"""
        WITH test_events AS (
            {test_union}
        )
        SELECT d.id, d.name,
               COUNT(*) AS tests,
               COUNT(*) FILTER (WHERE s.report_date BETWEEN :start AND :end) AS tests_reported
        FROM test_events t
        JOIN glims_samples s ON s.sample_id = t.sample_id
        JOIN glims_dispensaries d ON d.id = s.dispensary_id
        WHERE t.d BETWEEN :start AND :end
        GROUP BY d.id, d.name
        ORDER BY tests DESC
        LIMIT :limit
    """
    rows = session.execute(text(sql), params).all()
    customers = [
        TopCustomerItem(
            id=row.id,
            name=row.name,
            tests=row.tests,
            tests_reported=row.tests_reported,
        )
        for row in rows
    ]
    return TopCustomersResponse(customers=customers)


@router.get("/tests/by-label", response_model=TestsByLabelResponse)
def get_tests_by_label(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    sample_type: Optional[str] = Query(None),
    session: Session = Depends(get_db_session),
) -> TestsByLabelResponse:
    start, end = _parse_dates(date_from, date_to)
    params = {"start": start, "end": end}
    labels: list[TestsByLabelItem] = []
    for label, (table, date_a, date_b) in ASSAY_TABLES.items():
        sql = f"""
            SELECT COUNT(*) AS c, s.adult_use_medical
            FROM {table} r
            JOIN glims_samples s ON s.sample_id = r.sample_id
            WHERE COALESCE(r.{date_a}, r.{date_b}, s.date_received) BETWEEN :start AND :end
            {"AND s.adult_use_medical = :sample_type" if sample_type and sample_type != 'All' else ""}
            GROUP BY s.adult_use_medical
        """
        if sample_type and sample_type != 'All':
            params["sample_type"] = sample_type
        
        total_for_label = 0
        breakdown = {}
        for row in session.execute(text(sql), params):
            total_for_label += row.c
            breakdown[row.adult_use_medical or "Unknown"] = row.c
        
        labels.append(TestsByLabelItem(key=label, count=total_for_label, breakdown=breakdown))
    labels.sort(key=lambda x: x.count, reverse=True)
    return TestsByLabelResponse(labels=labels)


@router.get("/tat-daily", response_model=TatDailyResponse)
def get_tat_daily(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    sample_type: Optional[str] = Query(None),
    tat_target_hours: float = Query(72.0, ge=1.0),
    moving_average_window: int = Query(7, ge=1, le=30),
    session: Session = Depends(get_db_session),
) -> TatDailyResponse:
    start, end = _parse_dates(date_from, date_to)
    params = {"start": start, "end": end, "tat_target_hours": tat_target_hours}
    sql = f"""
        SELECT
            s.report_date AS d,
            AVG(EXTRACT(EPOCH FROM (s.report_date::timestamp - s.date_received::timestamp))/3600.0) AS avg_hours,
            COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM (s.report_date::timestamp - s.date_received::timestamp))/3600.0 <= :tat_target_hours) AS within_tat,
            COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM (s.report_date::timestamp - s.date_received::timestamp))/3600.0 > :tat_target_hours) AS beyond_tat
        FROM glims_samples s
        WHERE s.report_date BETWEEN :start AND :end
          AND s.date_received IS NOT NULL
          {"AND s.adult_use_medical = :sample_type" if sample_type and sample_type != 'All' else ""}
        GROUP BY s.report_date
        ORDER BY s.report_date
    """
    if sample_type and sample_type != 'All':
        params["sample_type"] = sample_type
    rows = session.execute(text(sql), params).all()
    points: list[TatDailyPoint] = []
    for row in rows:
        points.append(
            TatDailyPoint(
                date=row.d,
                average_hours=float(row.avg_hours) if row.avg_hours is not None else None,
                within_tat=row.within_tat or 0,
                beyond_tat=row.beyond_tat or 0,
            )
        )

    # moving average
    for idx, point in enumerate(points):
        window_start = max(0, idx - moving_average_window + 1)
        window = points[window_start : idx + 1]
        values = [p.average_hours for p in window if p.average_hours is not None]
        point.moving_average_hours = float(sum(values) / len(values)) if values else None

    return TatDailyResponse(points=points)
