"""API v2 TAT analytics for GLIMS samples."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from downloader_qbench_data.api.dependencies import get_db_session, require_active_user
from downloader_qbench_data.api.schemas.glims_tat import GlimsTatItem, GlimsTatResponse, GlimsTatStats

router = APIRouter(
    prefix="/api/v2/glims/tat",
    tags=["glims-tat"],
    dependencies=[Depends(require_active_user)],
)

# Result tables that represent assays linked to glims_samples.sample_id
ASSAY_TABLES = (
    "glims_cn_results",
    "glims_mb_results",
    "glims_hm_results",
    "glims_wa_results",
    "glims_ps_results",
    "glims_tp_results",
    "glims_rs_results",
    "glims_my_results",
    "glims_mc_results",
    "glims_pn_results",
    "glims_ffm_results",
    "glims_lw_results",
)


def _format_open_time_label(hours: Optional[float]) -> str:
    if hours is None:
        return "--"
    total_hours = int(round(max(0.0, float(hours))))
    days, remaining_hours = divmod(total_hours, 24)
    parts = []
    if days:
        parts.append(f"{days}d")
    parts.append(f"{remaining_hours}h")
    return " ".join(parts)


def _resolve_dates(date_from: Optional[date], date_to: Optional[date], lookback_days: Optional[int]) -> tuple[date, date]:
    """Return (start, end) inclusive date range with sensible defaults."""

    end = date_to or datetime.utcnow().date()
    lb = 30 if lookback_days is None else max(1, lookback_days)
    start = date_from or (end - timedelta(days=lb - 1))
    if start > end:
        start, end = end, start
    return start, end


@router.get("/slowest", response_model=GlimsTatResponse, status_code=status.HTTP_200_OK)
def get_slowest_tat_samples(
    date_from: Optional[date] = Query(None, description="Include samples reported on/after this date (UTC)"),
    date_to: Optional[date] = Query(None, description="Include samples reported on/before this date (UTC)"),
    dispensary_query: Optional[str] = Query(None, description="Filter by dispensary id or name fragment"),
    min_open_hours: float = Query(0.0, ge=0.0, description="Minimum open hours (received -> reported)"),
    outlier_threshold_hours: Optional[float] = Query(72.0, ge=0.0, description="Threshold to flag outliers"),
    lookback_days: Optional[int] = Query(None, ge=1, le=180, description="Lookback days when date_from is omitted"),
    limit: int = Query(50, ge=1, le=200, description="Maximum samples to return"),
    session: Session = Depends(get_db_session),
) -> GlimsTatResponse:
    """
    Return reported samples with the longest turnaround time (date_received -> report_date) in GLIMS.
    """

    start_date, end_date = _resolve_dates(date_from, date_to, lookback_days)
    min_open = max(0.0, float(min_open_hours))
    threshold = max(0.0, float(outlier_threshold_hours)) if outlier_threshold_hours is not None else None
    effective_limit = max(1, min(limit, 200))

    filters = [
        "s.report_date IS NOT NULL",
        "s.date_received IS NOT NULL",
        "s.report_date BETWEEN :start_date AND :end_date",
    ]
    params: dict[str, object] = {
        "start_date": start_date,
        "end_date": end_date,
        "min_open": min_open,
    }

    if dispensary_query:
        q = dispensary_query.strip()
        if q:
            try:
                disp_id = int(q)
                filters.append("s.dispensary_id = :dispensary_id")
                params["dispensary_id"] = disp_id
            except ValueError:
                filters.append("(d.name ILIKE :disp_name OR s.client_name ILIKE :disp_name)")
                params["disp_name"] = f"%{q}%"

    open_hours_expr = "EXTRACT(EPOCH FROM (s.report_date::timestamp - s.date_received::timestamp))/3600.0"
    filters_clause = " AND ".join(filters)

    stats_sql = f"""
        SELECT
            COUNT(*) AS total,
            AVG({open_hours_expr}) AS avg_open,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY {open_hours_expr}) AS p95_open
        FROM glims_samples s
        LEFT JOIN glims_dispensaries d ON d.id = s.dispensary_id
        WHERE {filters_clause}
          AND {open_hours_expr} >= :min_open
    """
    stats_row = session.execute(text(stats_sql), params).one()
    total_samples = int(stats_row.total or 0)
    avg_hours = float(stats_row.avg_open) if stats_row.avg_open is not None else None
    p95_hours = float(stats_row.p95_open) if stats_row.p95_open is not None else None

    tests_union_sql = " UNION ALL ".join(f"SELECT sample_id FROM {table}" for table in ASSAY_TABLES)
    query_sql = f"""
        WITH tests_union AS (
            {tests_union_sql}
        ),
        tests_agg AS (
            SELECT sample_id, COUNT(*) AS tests_count
            FROM tests_union
            GROUP BY sample_id
        )
        SELECT
            s.sample_id,
            s.dispensary_id,
            d.name AS dispensary_name,
            s.date_received,
            s.report_date,
            COALESCE(t.tests_count, 0) AS tests_count,
            {open_hours_expr} AS open_hours
        FROM glims_samples s
        LEFT JOIN tests_agg t ON t.sample_id = s.sample_id
        LEFT JOIN glims_dispensaries d ON d.id = s.dispensary_id
        WHERE {filters_clause}
          AND {open_hours_expr} >= :min_open
        ORDER BY open_hours DESC, s.report_date DESC
        LIMIT :limit
    """
    params["limit"] = effective_limit
    rows = session.execute(text(query_sql), params).all()

    items: list[GlimsTatItem] = []
    for row in rows:
        open_hours_val = float(row.open_hours) if row.open_hours is not None else 0.0
        items.append(
            GlimsTatItem(
                sample_id=row.sample_id,
                dispensary_id=row.dispensary_id,
                dispensary_name=row.dispensary_name,
                date_received=row.date_received,
                report_date=row.report_date,
                tests_count=int(row.tests_count or 0),
                open_time_hours=open_hours_val,
                open_time_label=_format_open_time_label(open_hours_val),
                is_outlier=threshold is not None and open_hours_val >= threshold,
            )
        )

    stats = GlimsTatStats(
        total_samples=total_samples,
        average_open_hours=avg_hours,
        percentile_95_open_hours=p95_hours,
        threshold_hours=threshold,
    )
    return GlimsTatResponse(stats=stats, items=items)
