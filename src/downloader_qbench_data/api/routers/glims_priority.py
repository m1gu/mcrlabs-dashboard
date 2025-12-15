"""API v2 priority samples endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from downloader_qbench_data.api.dependencies import get_db_session, require_active_user
from downloader_qbench_data.api.schemas.glims_priority import (
    PriorityHeatmapItem,
    PriorityHeatmapResponse,
    PrioritySampleItem,
    PrioritySampleResponse,
    PriorityTestItem,
)

router = APIRouter(
    prefix="/api/v2/glims/priority",
    tags=["glims-priority"],
    dependencies=[Depends(require_active_user)],
)

# Mapping: label -> (table, start_date_column)
ASSAY_START_MAP = {
    "CN": ("glims_cn_results", "start_date"),
    "MB": ("glims_mb_results", "tempo_prep_date"),  # best available "start" proxy
    "HM": ("glims_hm_results", "start_date"),
    "WA": ("glims_wa_results", "start_date"),
    "PS": ("glims_ps_results", "start_date"),
    "TP": ("glims_tp_results", "start_date"),
    "RS": ("glims_rs_results", "start_date"),
    "MY": ("glims_my_results", "start_date"),
    "MC": ("glims_mc_results", "start_date"),
    "PN": ("glims_pn_results", "start_date"),
    "FFM": ("glims_ffm_results", "analysis_date"),
    "LW": ("glims_lw_results", "run_date"),
    "HO": ("glims_ho_results", "start_date"),
}


EXCLUDE_PATTERN = r"(-HO[12](-\d+)?)$|(-(1|2|3|N))$"


def _min_days(min_days_overdue: Optional[int]) -> int:
    if min_days_overdue is None:
        return 3
    return max(0, min_days_overdue)


@router.get("/most-overdue", response_model=PrioritySampleResponse, status_code=status.HTTP_200_OK)
def get_most_overdue_samples(
    min_days_overdue: Optional[int] = Query(3, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> PrioritySampleResponse:
    """
    Return samples with longest open time (date_received until now), excluding HO / -N suffixes.
    A sample is considered open/overdue if:
    - date_received is set AND open_days >= min_days_overdue, AND
    - (report_date is NULL OR tests_complete < tests_total).
    Tests are complete when analytes IS NOT NULL.
    """
    min_days = _min_days(min_days_overdue)
    now = datetime.utcnow()

    # Build union of tests
    union_parts = []
    for label, (table, start_col) in ASSAY_START_MAP.items():
        union_parts.append(
            f"""
            SELECT '{label}' AS label,
                   sample_id,
                   {start_col}::date AS start_date,
                   analytes,
                   status
            FROM {table}
            """
        )
    tests_union_sql = " UNION ALL ".join(union_parts)

    sql = f"""
        WITH tests_union AS (
            {tests_union_sql}
        ),
        tests_agg AS (
            SELECT sample_id,
                   COUNT(*) AS tests_total,
                   COUNT(*) FILTER (WHERE status = 'Completed') AS tests_complete
            FROM tests_union
            GROUP BY sample_id
        ),
        candidates AS (
            SELECT
                s.sample_id,
                s.client_name,
                s.dispensary_id,
                d.name AS dispensary_name,
                s.status,
                s.date_received,
                s.report_date,
                COALESCE(ta.tests_total, 0) AS tests_total,
                COALESCE(ta.tests_complete, 0) AS tests_complete,
                EXTRACT(EPOCH FROM (:now - s.date_received::timestamp))/3600.0 AS open_hours
            FROM glims_samples s
            LEFT JOIN tests_agg ta ON ta.sample_id = s.sample_id
            LEFT JOIN glims_dispensaries d ON d.id = s.dispensary_id
            WHERE s.date_received IS NOT NULL
              AND s.sample_id !~ :exclude_pattern
        )
        SELECT *
        FROM candidates
        WHERE report_date IS NULL
          AND tests_total > 0
          AND tests_complete < tests_total
          AND open_hours >= (:min_days * 24)
        ORDER BY open_hours DESC
        LIMIT :limit
    """
    params = {
        "now": now,
        "min_days": min_days,
        "limit": limit,
        "exclude_pattern": EXCLUDE_PATTERN,
    }
    rows = session.execute(text(sql), params).all()
    sample_ids = [row.sample_id for row in rows]
    if not sample_ids:
        return PrioritySampleResponse(samples=[])

    # Fetch tests for these samples
    tests_sql = f"""
        SELECT t.sample_id, t.label, t.start_date, (t.status = 'Completed') AS complete, t.status
        FROM ({tests_union_sql}) t
        WHERE t.sample_id = ANY(:sample_ids)
    """
    tests_rows = session.execute(text(tests_sql), {"sample_ids": sample_ids}).all()
    tests_by_sample: dict[str, list[PriorityTestItem]] = {}
    for t in tests_rows:
        tests_by_sample.setdefault(t.sample_id, []).append(
            PriorityTestItem(label=t.label, start_date=t.start_date, complete=bool(t.complete), status=t.status)
        )

    samples: list[PrioritySampleItem] = []
    for row in rows:
        samples.append(
            PrioritySampleItem(
                sample_id=row.sample_id,
                client_name=row.client_name,
                dispensary_id=row.dispensary_id,
                dispensary_name=row.dispensary_name,
                date_received=row.date_received,
                report_date=row.report_date,
                open_hours=float(row.open_hours) if row.open_hours is not None else None,
                tests_total=row.tests_total,
                tests_complete=row.tests_complete,
                tests=tests_by_sample.get(row.sample_id, []),
                status=row.status,
            )
        )
    return PrioritySampleResponse(samples=samples)


@router.get("/overdue-heatmap", response_model=PriorityHeatmapResponse, status_code=status.HTTP_200_OK)
def get_overdue_heatmap(
    min_days_overdue: Optional[int] = Query(3, ge=0),
    bucket: str = Query("week", regex="^(day|week)$"),
    session: Session = Depends(get_db_session),
) -> PriorityHeatmapResponse:
    """
    Heatmap-like aggregation: counts of overdue samples by dispensary and period (day/week).
    Overdue definition matches most-overdue endpoint.
    """
    min_days = _min_days(min_days_overdue)
    bucket_expr = "date_trunc('week', s.date_received)" if bucket == "week" else "date_trunc('day', s.date_received)"
    now = datetime.utcnow()
    sql = f"""
        WITH tests_union AS (
            { " UNION ALL ".join(
                f"SELECT sample_id, analytes, status FROM {table}" for table, _ in ASSAY_START_MAP.values()
            ) }
        ),
        tests_agg AS (
            SELECT sample_id,
                   COUNT(*) AS tests_total,
                   COUNT(*) FILTER (WHERE status = 'Completed') AS tests_complete
            FROM tests_union
            GROUP BY sample_id
        )
        SELECT
            s.dispensary_id,
            d.name AS dispensary_name,
            {bucket_expr}::date AS period_start,
            COUNT(*) AS count
        FROM glims_samples s
        LEFT JOIN tests_agg ta ON ta.sample_id = s.sample_id
        LEFT JOIN glims_dispensaries d ON d.id = s.dispensary_id
        WHERE s.date_received IS NOT NULL
          AND s.sample_id !~ :exclude_pattern
          AND (s.report_date IS NULL OR COALESCE(ta.tests_total,0)=0 OR COALESCE(ta.tests_complete,0) < COALESCE(ta.tests_total,0))
          AND EXTRACT(EPOCH FROM (:now - s.date_received::timestamp))/3600.0 >= (:min_days * 24)
        GROUP BY s.dispensary_id, d.name, period_start
        ORDER BY period_start, dispensary_name
    """
    params = {
        "now": now,
        "min_days": min_days,
        "exclude_pattern": EXCLUDE_PATTERN,
    }
    rows = session.execute(text(sql), params).all()
    buckets = [
        PriorityHeatmapItem(
            dispensary_id=row.dispensary_id,
            dispensary_name=row.dispensary_name,
            period_start=row.period_start,
            count=row.count,
        )
        for row in rows
    ]
    return PriorityHeatmapResponse(buckets=buckets)
