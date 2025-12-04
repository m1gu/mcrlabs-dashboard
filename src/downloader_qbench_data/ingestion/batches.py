"""Ingestion routines for QBench batches."""

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
    EntityRecoveryService,
    attempt_dependency_recovery,
)
from downloader_qbench_data.ingestion.utils import SkippedEntity, ensure_int_list, parse_qbench_datetime
from downloader_qbench_data.storage import Batch, Sample, SyncCheckpoint, Test, session_scope

LOGGER = logging.getLogger(__name__)
ENTITY_NAME = "batches"
API_MAX_PAGE_SIZE = 50


@dataclass
class BatchSyncSummary:
    """Aggregated statistics for a batch sync run."""

    processed: int = 0
    skipped_old: int = 0
    skipped_missing_dependency: int = 0
    pages_seen: int = 0
    last_synced_at: Optional[datetime] = None
    total_pages: Optional[int] = None
    start_page: int = 1
    skipped_entities: list[SkippedEntity] = field(default_factory=list)
    dependencies_recovered: int = 0


def sync_batches(
    settings: Optional[AppSettings] = None,
    *,
    full_refresh: bool = False,
    page_size: Optional[int] = None,
    include_raw_worksheet_data: bool = False,
    progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    start_datetime: Optional[datetime] = None,
    end_datetime: Optional[datetime] = None,
    ignore_checkpoint: bool = False,
    dependency_resolver: Optional[EntityRecoveryService] = None,
    dependency_max_attempts: int = 3,
) -> BatchSyncSummary:
    """Synchronise batch data from QBench into PostgreSQL."""

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
        known_samples = _load_sample_ids(session)
        known_tests = _load_test_ids(session)

    summary = BatchSyncSummary(last_synced_at=last_synced_at, start_page=start_page)
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
                payload = client.list_batches(
                    page_num=current_page,
                    page_size=effective_page_size,
                    include_raw_worksheet_data=include_raw_worksheet_data,
                    sort_by="date_created" if window_mode else None,
                    sort_order="desc" if window_mode else None,
                )
                total_pages = payload.get("total_pages") or total_pages
                summary.total_pages = total_pages
                batches = payload.get("data") or []
                if not batches:
                    break

                summary.pages_seen += 1
                records_to_upsert: list[dict] = []
                for item in batches:
                    batch_id = item["id"]
                    created_at = parse_qbench_datetime(item.get("date_created"))

                    if (
                        not full_refresh
                        and last_id is not None
                        and batch_id <= last_id
                    ):
                        summary.skipped_old += 1
                        continue

                    if window_mode and start_datetime and created_at and created_at < start_datetime:
                        stop_after_page = True
                        break

                    if (not window_mode) and start_datetime and created_at and created_at < start_datetime:
                        summary.skipped_old += 1
                        continue

                    if end_datetime and created_at and created_at > end_datetime:
                        continue

                    sample_ids = ensure_int_list(item.get("sample_ids"))
                    test_ids = ensure_int_list(item.get("test_ids"))

                    dependencies_failed = False
                    if dependency_resolver:
                        for sample_id in sample_ids:
                            if sample_id in known_samples:
                                continue
                            outcome = attempt_dependency_recovery(
                                dependency_resolver,
                                "samples",
                                sample_id,
                                max_attempts=dependency_max_attempts,
                            )
                            if outcome.succeeded:
                                known_samples.add(sample_id)
                                summary.dependencies_recovered += 1
                                continue
                            dependencies_failed = True
                            summary.skipped_missing_dependency += 1
                            summary.skipped_entities.append(
                                SkippedEntity(
                                    entity_id=batch_id,
                                    reason="unknown_sample",
                                    details={
                                        "sample_id": sample_id,
                                        "recovery_attempts": outcome.attempts,
                                        "recovery_error": outcome.error,
                                    },
                                )
                            )
                            break

                        if not dependencies_failed:
                            for test_id_ref in test_ids:
                                if test_id_ref in known_tests:
                                    continue
                                outcome = attempt_dependency_recovery(
                                    dependency_resolver,
                                    "tests",
                                    test_id_ref,
                                    max_attempts=dependency_max_attempts,
                                )
                                if outcome.succeeded:
                                    known_tests.add(test_id_ref)
                                    summary.dependencies_recovered += 1
                                    continue
                                dependencies_failed = True
                                summary.skipped_missing_dependency += 1
                                summary.skipped_entities.append(
                                    SkippedEntity(
                                        entity_id=batch_id,
                                        reason="unknown_test",
                                        details={
                                            "test_id": test_id_ref,
                                            "recovery_attempts": outcome.attempts,
                                            "recovery_error": outcome.error,
                                        },
                                    )
                                )
                                break

                        if dependencies_failed:
                            continue
                    else:
                        known_samples.update(sample_ids)
                        known_tests.update(test_ids)

                    record = {
                        "id": batch_id,
                        "assay_id": item.get("assay_id"),
                        "display_name": item.get("display_name"),
                        "date_created": created_at,
                        "date_prepared": parse_qbench_datetime(item.get("date_prepared")),
                        "last_updated": parse_qbench_datetime(item.get("last_updated")),
                        "sample_ids": sample_ids,
                        "test_ids": test_ids,
                        "raw_payload": item,
                    }
                    records_to_upsert.append(record)
                    summary.processed += 1
                    if created_at and (max_synced_at is None or created_at > max_synced_at):
                        max_synced_at = created_at
                    if max_id is None or batch_id > max_id:
                        max_id = batch_id

                _persist_batch(records_to_upsert, current_page, max_synced_at, max_id, settings)
                if progress_callback:
                    progress_callback(summary.pages_seen, total_pages)

                if stop_after_page:
                    break
                if total_pages and current_page >= total_pages:
                    break
                current_page += 1

    except Exception as exc:
        LOGGER.exception("Batch sync failed on page %s", current_page)
        _mark_checkpoint_failed(current_page, settings, error=exc)
        raise

    _mark_checkpoint_completed(current_page, max_synced_at, max_id, settings)
    summary.last_synced_at = max_synced_at
    return summary


def _persist_batch(
    rows: Iterable[dict],
    current_page: int,
    max_synced_at: Optional[datetime],
    max_id: Optional[int],
    settings: AppSettings,
) -> None:
    """Persist a batch of batches and update checkpoint progress."""

    with session_scope(settings) as session:
        checkpoint = _get_or_create_checkpoint(session)
        checkpoint.last_cursor = current_page
        checkpoint.status = "running"
        checkpoint.failed = False
        checkpoint.message = None

        if rows:
            insert_stmt = insert(Batch).values(list(rows))
            update_stmt = {
                "assay_id": insert_stmt.excluded.assay_id,
                "display_name": insert_stmt.excluded.display_name,
                "date_created": insert_stmt.excluded.date_created,
                "date_prepared": insert_stmt.excluded.date_prepared,
                "last_updated": insert_stmt.excluded.last_updated,
                "sample_ids": insert_stmt.excluded.sample_ids,
                "test_ids": insert_stmt.excluded.test_ids,
                "raw_payload": insert_stmt.excluded.raw_payload,
                "fetched_at": func.now(),
            }
            session.execute(insert_stmt.on_conflict_do_update(index_elements=[Batch.id], set_=update_stmt))
            checkpoint.last_synced_at = max_synced_at
            checkpoint.last_id = max_id


def _load_sample_ids(session: Session) -> set[int]:
    result = session.execute(select(Sample.id))
    return {row[0] for row in result}


def _load_test_ids(session: Session) -> set[int]:
    result = session.execute(select(Test.id))
    return {row[0] for row in result}


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
