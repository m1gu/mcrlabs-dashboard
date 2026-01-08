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
    settings: AppSettings = Depends(get_app_settings),
    session: Session = Depends(get_db_session),
) -> OverviewSummary:
    start, end = _parse_dates(date_from, date_to)

    filters = ["s.date_received BETWEEN :start AND :end"]
    params = {"start": start, "end": end}
    if dispensary_id:
        filters.append("s.dispensary_id = :dispensary_id")
        params["dispensary_id"] = dispensary_id
    
    filters.append("s.status NOT IN ('Cancelled', 'Destroyed')")
    # Query 1: Intake Metrics (based on date_received)
    intake_where = " AND ".join(filters) # Already defined as date_received filter
    
    intake_sql = f"""
        SELECT
            COUNT(*) AS samples,
            MAX(GREATEST(s.date_received, s.report_date)) AS last_updated_at
        FROM glims_samples s
        WHERE {intake_where}
    """
    intake_row = session.execute(text(intake_sql), params).one()

    # Query New Customers from the dedicated table
    new_customers_sql = """
        SELECT COUNT(*)
        FROM glims_new_customers
        WHERE date_created BETWEEN :start AND :end
    """
    new_customers_params = {"start": start, "end": end}
    
    if dispensary_id:
        # Get the name of the dispensary to filter glims_new_customers
        disp_name = session.execute(
            text("SELECT name FROM glims_dispensaries WHERE id = :id"),
            {"id": dispensary_id}
        ).scalar()
        if disp_name:
            new_customers_sql += " AND client_name = :name"
            new_customers_params["name"] = disp_name
        else:
            # If dispensary doesn't exist, count is 0
            new_customers_sql += " AND 1=0"

    new_customers_count = session.execute(text(new_customers_sql), new_customers_params).scalar() or 0

    # Query 2: Output Metrics (based on report_date)
    # Align 'Reports' KPI with the Activity Chart (Sum of daily reported)
    output_filters = ["s.report_date BETWEEN :start AND :end"]
    if dispensary_id:
        output_filters.append("s.dispensary_id = :dispensary_id")
    output_where = " AND ".join(output_filters)

    output_sql = f"""
        SELECT
            COUNT(*) AS reports,
            AVG(EXTRACT(EPOCH FROM (s.report_date::timestamp - s.date_received::timestamp))/3600.0) AS avg_tat_hours
        FROM glims_samples s
        WHERE {output_where}
    """
    output_row = session.execute(text(output_sql), params).one()

    sync_sql = """
        SELECT finished_at
        FROM glims_sync_runs
        WHERE status = 'success'
        ORDER BY finished_at DESC
        LIMIT 1
    """
    last_sync_at = session.execute(text(sync_sql)).scalar_one_or_none()

    tests_total = 0
    for label, (table, date_a, date_b) in ASSAY_TABLES.items():
        test_sql = f"""
            SELECT COUNT(*) AS c
            FROM {table} r
            JOIN glims_samples s ON s.sample_id = r.sample_id
            WHERE COALESCE(r.{date_a}, r.{date_b}, s.date_received) BETWEEN :start AND :end
            {"AND s.dispensary_id = :dispensary_id" if dispensary_id else ""}
        """
        tests_total += session.execute(text(test_sql), params).scalar_one()

    return OverviewSummary(
        samples=intake_row.samples or 0,
        tests=tests_total,
        customers=new_customers_count,
        reports=output_row.reports or 0,
        avg_tat_hours=float(output_row.avg_tat_hours) if output_row.avg_tat_hours is not None else None,
        last_sync_at=last_sync_at,
        last_updated_at=intake_row.last_updated_at,
    )


@router.get("/activity", response_model=ActivityResponse)
def get_activity(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    dispensary_id: Optional[int] = Query(None),
    session: Session = Depends(get_db_session),
) -> ActivityResponse:
    start, end = _parse_dates(date_from, date_to)
    params = {"start": start, "end": end}
    samples_where = ["date_received BETWEEN :start AND :end"]
    if dispensary_id:
        samples_where.append("s.dispensary_id = :dispensary_id")

    samples_sql = f"""
        SELECT date_received AS d, adult_use_medical, COUNT(*) AS c
        FROM glims_samples s
        WHERE {" AND ".join(samples_where)}
        GROUP BY date_received, adult_use_medical
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

    reported_sql = f"""
        SELECT report_date AS d, COUNT(*) AS c
        FROM glims_samples s
        WHERE report_date BETWEEN :start AND :end {disp_clause}
        GROUP BY report_date
    """
    reported_map = {row.d: row.c for row in session.execute(text(reported_sql), params)}

    tests_map: dict[date, int] = {}
    for label, (table, date_a, date_b) in ASSAY_TABLES.items():
        test_sql = f"""
            SELECT COALESCE(r.{date_a}, r.{date_b}, s.date_received) AS d, COUNT(*) AS c
            FROM {table} r
            JOIN glims_samples s ON s.sample_id = r.sample_id
            WHERE COALESCE(r.{date_a}, r.{date_b}, s.date_received) BETWEEN :start AND :end 
            {disp_clause}
            GROUP BY COALESCE(r.{date_a}, r.{date_b}, s.date_received)
        """
        for row in session.execute(text(test_sql), params):
            tests_map[row.d] = tests_map.get(row.d, 0) + row.c

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
    session: Session = Depends(get_db_session),
) -> TestsByLabelResponse:
    start, end = _parse_dates(date_from, date_to)
    params = {"start": start, "end": end}
    labels: list[TestsByLabelItem] = []
    for label, (table, date_a, date_b) in ASSAY_TABLES.items():
        sql = f"""
            SELECT COUNT(*) AS c
            FROM {table} r
            JOIN glims_samples s ON s.sample_id = r.sample_id
            WHERE COALESCE(r.{date_a}, r.{date_b}, s.date_received) BETWEEN :start AND :end
        """
        count = session.execute(text(sql), params).scalar_one()
        labels.append(TestsByLabelItem(key=label, count=count))
    labels.sort(key=lambda x: x.count, reverse=True)
    return TestsByLabelResponse(labels=labels)


@router.get("/tat-daily", response_model=TatDailyResponse)
def get_tat_daily(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    tat_target_hours: float = Query(72.0, ge=1.0),
    moving_average_window: int = Query(7, ge=1, le=30),
    session: Session = Depends(get_db_session),
) -> TatDailyResponse:
    start, end = _parse_dates(date_from, date_to)
    params = {"start": start, "end": end, "tat_target_hours": tat_target_hours}
    sql = """
        SELECT
            report_date AS d,
            AVG(EXTRACT(EPOCH FROM (report_date::timestamp - date_received::timestamp))/3600.0) AS avg_hours,
            COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM (report_date::timestamp - date_received::timestamp))/3600.0 <= :tat_target_hours) AS within_tat,
            COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM (report_date::timestamp - date_received::timestamp))/3600.0 > :tat_target_hours) AS beyond_tat
        FROM glims_samples
        WHERE report_date BETWEEN :start AND :end
          AND date_received IS NOT NULL
        GROUP BY report_date
        ORDER BY report_date
    """
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
