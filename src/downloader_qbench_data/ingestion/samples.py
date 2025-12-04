"""Ingestion routines for QBench samples."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from downloader_qbench_data.clients.qbench import QBenchClient
from downloader_qbench_data.config import AppSettings, get_settings
from downloader_qbench_data.ingestion.recovery import (
    DependencyRecoveryOutcome,
    EntityRecoveryService,
    attempt_dependency_recovery,
)
from downloader_qbench_data.ingestion.utils import (
    SkippedEntity,
    ensure_int_list,
    parse_qbench_datetime,
    safe_int,
    safe_decimal,
)
from downloader_qbench_data.storage import Order, Sample, SyncCheckpoint, session_scope

LOGGER = logging.getLogger(__name__)
ENTITY_NAME = "samples"
API_MAX_PAGE_SIZE = 50


@dataclass
class SampleSyncSummary:
    """Aggregated statistics for a sample sync run."""

    processed: int = 0
    skipped_missing_order: int = 0
    skipped_unknown_order: int = 0
    skipped_old: int = 0
    pages_seen: int = 0
    last_synced_at: Optional[datetime] = None
    total_pages: Optional[int] = None
    start_page: int = 1
    last_id: Optional[int] = None
    skipped_entities: list[SkippedEntity] = field(default_factory=list)
    dependencies_recovered: int = 0


def sync_samples(
    settings: Optional[AppSettings] = None,
    *,
    full_refresh: bool = False,
    page_size: Optional[int] = None,
    progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    start_datetime: Optional[datetime] = None,
    end_datetime: Optional[datetime] = None,
    ignore_checkpoint: bool = False,
    dependency_resolver: Optional[EntityRecoveryService] = None,
    dependency_max_attempts: int = 3,
) -> SampleSyncSummary:
    """Synchronise sample data from QBench into PostgreSQL."""

    settings = settings or get_settings()
    effective_page_size = min(page_size or settings.page_size, API_MAX_PAGE_SIZE)

    with session_scope(settings) as session:
        checkpoint = _get_or_create_checkpoint(session)
        if full_refresh:
            checkpoint.last_synced_at = None
            checkpoint.last_id = None
            checkpoint.last_cursor = 1
        start_page = checkpoint.last_cursor or 1
        last_synced_at = checkpoint.last_synced_at
        last_id = checkpoint.last_id
        if ignore_checkpoint:
            start_page = 1
            last_synced_at = None
            last_id = None
        checkpoint.status = "running"
        checkpoint.failed = False
        checkpoint.message = None
        known_orders = _load_order_ids(session)

    summary = SampleSyncSummary(last_synced_at=last_synced_at, start_page=start_page, last_id=last_id)
    baseline_synced_at = last_synced_at
    max_synced_at = last_synced_at
    max_id = last_id
    current_page = start_page
    window_mode = bool(ignore_checkpoint and start_datetime)

    try:
        with QBenchClient(
            base_url=settings.qbench.base_url,
            client_id=settings.qbench.client_id,
            client_secret=settings.qbench.client_secret,
            token_url=settings.qbench.token_url,
        ) as client:
            total_pages: Optional[int] = None
            while True:
                stop_after_page = False
                sort_by = "date_created" if window_mode else "id"
                sort_order = "desc" if window_mode else "asc"
                payload = client.list_samples(
                    page_num=current_page,
                    page_size=effective_page_size,
                    sort_by=sort_by,
                    sort_order=sort_order,
                )
                total_pages = payload.get("total_pages") or total_pages
                summary.total_pages = total_pages
                samples = payload.get("data") or []
                if not samples:
                    break

                summary.pages_seen += 1
                records_to_upsert = []
                for item in samples:
                    sample_id = item["id"]
                    if (
                        not full_refresh
                        and last_id is not None
                        and sample_id <= last_id
                    ):
                        summary.skipped_old += 1
                        continue

                    order_id = item.get("order_id")
                    if not order_id:
                        summary.skipped_missing_order += 1
                        summary.skipped_entities.append(
                            SkippedEntity(entity_id=sample_id, reason="missing_order_id")
                        )
                        continue

                    if order_id not in known_orders:
                        recovery_outcome: Optional[DependencyRecoveryOutcome] = None
                        if dependency_resolver:
                            recovery_outcome = attempt_dependency_recovery(
                                dependency_resolver,
                                "orders",
                                order_id,
                                max_attempts=dependency_max_attempts,
                            )
                            if recovery_outcome.succeeded:
                                known_orders.add(order_id)
                                summary.dependencies_recovered += 1

                        if order_id not in known_orders:
                            summary.skipped_unknown_order += 1
                            LOGGER.warning(
                                "Skipping sample %s because order %s does not exist locally%s",
                                item.get("id"),
                                order_id,
                                ""
                                if not recovery_outcome or recovery_outcome.succeeded
                                else f" (recovery failed after {recovery_outcome.attempts} attempts)",
                            )
                            summary.skipped_entities.append(
                                SkippedEntity(
                                    entity_id=sample_id,
                                    reason="unknown_order",
                                    details={
                                        "order_id": order_id,
                                        "recovery_attempts": (
                                            recovery_outcome.attempts if recovery_outcome else 0
                                        ),
                                        "recovery_error": (
                                            recovery_outcome.error if recovery_outcome else None
                                        ),
                                    },
                                )
                            )
                            continue

                    created_at = parse_qbench_datetime(item.get("date_created"))
                    if window_mode and start_datetime and created_at and created_at < start_datetime:
                        stop_after_page = True
                        break
                    if end_datetime and created_at and created_at > end_datetime:
                        continue
                    record = {
                        "id": item["id"],
                        "sample_name": item.get("sample_name") or item.get("description"),
                        "custom_formatted_id": item.get("custom_formatted_id"),
                        "metrc_id": item.get("leaf_id"),
                        "order_id": order_id,
                        "has_report": bool(item.get("has_report")),
                        "batch_ids": ensure_int_list(item.get("batches")),
                        "completed_date": parse_qbench_datetime(
                            item.get("completed_date") or item.get("complete_date")
                        ),
                        "date_created": created_at,
                        "start_date": parse_qbench_datetime(item.get("start_date")),
                        "matrix_type": item.get("matrix_type"),
                        "sample_type": (item.get("accessioning_type") or {}).get("value"),
                        "state": item.get("state"),
                        "test_count": safe_int(item.get("test_count")),
                        "sample_weight": safe_decimal(item.get("sample_weight")),
                        "raw_payload": item,
                    }
                    records_to_upsert.append(record)
                    summary.processed += 1
                    if created_at and (max_synced_at is None or created_at > max_synced_at):
                        max_synced_at = created_at
                    if max_id is None or sample_id > max_id:
                        max_id = sample_id

                _persist_batch(records_to_upsert, current_page, max_synced_at, max_id, settings)
                if progress_callback:
                    progress_callback(summary.pages_seen, total_pages)

                if stop_after_page:
                    break
                if total_pages and current_page >= total_pages:
                    break
                current_page += 1

    except Exception as exc:
        LOGGER.exception("Sample sync failed on page %s", current_page)
        _mark_checkpoint_failed(current_page, settings, error=exc)
        raise

    _mark_checkpoint_completed(current_page, max_synced_at, max_id, settings)
    summary.last_synced_at = max_synced_at
    summary.last_id = max_id
    return summary


def _persist_batch(
    rows: Iterable[dict],
    current_page: int,
    max_synced_at: Optional[datetime],
    max_id: Optional[int],
    settings: AppSettings,
) -> None:
    """Persist a batch of samples and update checkpoint progress."""

    with session_scope(settings) as session:
        checkpoint = _get_or_create_checkpoint(session)
        checkpoint.last_cursor = current_page
        checkpoint.status = "running"
        checkpoint.failed = False
        checkpoint.message = None

        if rows:
            insert_stmt = insert(Sample).values(list(rows))
            update_stmt = {
                "sample_name": insert_stmt.excluded.sample_name,
                "custom_formatted_id": insert_stmt.excluded.custom_formatted_id,
                "metrc_id": insert_stmt.excluded.metrc_id,
                "order_id": insert_stmt.excluded.order_id,
                "has_report": insert_stmt.excluded.has_report,
                "batch_ids": insert_stmt.excluded.batch_ids,
                "completed_date": insert_stmt.excluded.completed_date,
                "date_created": insert_stmt.excluded.date_created,
                "start_date": insert_stmt.excluded.start_date,
                "matrix_type": insert_stmt.excluded.matrix_type,
                "sample_type": insert_stmt.excluded.sample_type,
                "state": insert_stmt.excluded.state,
                "test_count": insert_stmt.excluded.test_count,
                "sample_weight": insert_stmt.excluded.sample_weight,
                "raw_payload": insert_stmt.excluded.raw_payload,
                "fetched_at": func.now(),
            }
            session.execute(insert_stmt.on_conflict_do_update(index_elements=[Sample.id], set_=update_stmt))
            checkpoint.last_synced_at = max_synced_at
            checkpoint.last_id = max_id


def _mark_checkpoint_completed(current_page: int, max_synced_at: Optional[datetime], max_id: Optional[int], settings: AppSettings) -> None:
    """Mark the checkpoint as completed."""

    with session_scope(settings) as session:
        checkpoint = _get_or_create_checkpoint(session)
        checkpoint.last_cursor = current_page
        checkpoint.last_synced_at = max_synced_at
        checkpoint.last_id = max_id
        checkpoint.status = "completed"
        checkpoint.failed = False
        checkpoint.message = None


def _mark_checkpoint_failed(current_page: int, settings: AppSettings, error: Exception) -> None:
    """Persist a failure state into the checkpoint."""

    with session_scope(settings) as session:
        checkpoint = _get_or_create_checkpoint(session)
        checkpoint.last_cursor = current_page
        checkpoint.failed = True
        checkpoint.status = "failed"
        checkpoint.message = str(error)


def _get_or_create_checkpoint(session: Session) -> SyncCheckpoint:
    """Fetch existing checkpoint or create one for the entity."""

    checkpoint = session.get(SyncCheckpoint, ENTITY_NAME)
    if not checkpoint:
        checkpoint = SyncCheckpoint(entity=ENTITY_NAME, status="never", failed=False)
        session.add(checkpoint)
        session.flush()
    return checkpoint


def _load_order_ids(session: Session) -> set[int]:
    """Load all order IDs present in the local database."""

    result = session.execute(select(Order.id))
    return {row[0] for row in result}
