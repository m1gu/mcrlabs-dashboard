"""Ingestion routines for QBench tests."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, Optional

import httpx
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
)
from downloader_qbench_data.storage import Sample, SyncCheckpoint, Test, session_scope

LOGGER = logging.getLogger(__name__)
ENTITY_NAME = "tests"
API_MAX_PAGE_SIZE = 50
DETAIL_SLEEP_SECONDS = 0.2
MAX_BAD_REQUEST_PAGES = 10


@dataclass
class TestSyncSummary:
    """Aggregated statistics for a test sync run."""

    processed: int = 0
    skipped_missing_sample: int = 0
    skipped_unknown_sample: int = 0
    skipped_old: int = 0
    pages_seen: int = 0
    last_synced_at: Optional[datetime] = None
    total_pages: Optional[int] = None
    start_page: int = 1
    last_id: Optional[int] = None
    detail_fetches: int = 0
    detail_bad_request_failures: int = 0
    page_bad_request_failures: int = 0
    skipped_entities: list[SkippedEntity] = field(default_factory=list)
    dependencies_recovered: int = 0


def sync_tests(
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
) -> TestSyncSummary:
    """Synchronise test data from QBench into PostgreSQL."""

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

    summary = TestSyncSummary(last_synced_at=last_synced_at, start_page=start_page, last_id=last_id)
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
                try:
                    payload = client.list_tests(
                        page_num=current_page,
                        page_size=effective_page_size,
                        sort_by="date_created" if window_mode else "id",
                        sort_order="desc" if window_mode else "asc",
                        include_raw_worksheet_data=True,
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == httpx.codes.BAD_REQUEST:
                        summary.page_bad_request_failures += 1
                        summary.skipped_entities.append(
                            SkippedEntity(
                                entity_id=f"page-{current_page}",
                                reason="list_tests_bad_request",
                                details={"status_code": exc.response.status_code},
                            )
                        )
                        LOGGER.warning(
                            "Skipping page %s due to repeated 400 BAD REQUEST when listing tests",
                            current_page,
                        )
                        if summary.page_bad_request_failures > MAX_BAD_REQUEST_PAGES:
                            LOGGER.error(
                                "Encountered %s pages with 400 BAD REQUEST when listing tests; aborting sync",
                                summary.page_bad_request_failures,
                            )
                            raise RuntimeError(
                                "Aborting test sync: too many pages returned 400 BAD REQUEST when listing tests"
                            ) from exc
                        current_page += 1
                        if total_pages and current_page > total_pages:
                            LOGGER.error(
                                "Next requested page %s exceeds reported total_pages %s after BAD REQUEST; aborting sync",
                                current_page,
                                total_pages,
                            )
                            raise RuntimeError(
                                "Aborting test sync: requested page exceeds total_pages after BAD REQUEST"
                            ) from exc
                        continue
                    raise
                total_pages = payload.get("total_pages") or total_pages
                summary.total_pages = total_pages
                tests = payload.get("data") or []
                if not tests:
                    break

                summary.pages_seen += 1
                records_to_upsert = []
                for item in tests:
                    test_id = item["id"]
                    if (
                        not full_refresh
                        and last_id is not None
                        and test_id <= last_id
                    ):
                        summary.skipped_old += 1
                        continue

                    sample_id = item.get("sample_id")
                    if not sample_id:
                        summary.skipped_missing_sample += 1
                        summary.skipped_entities.append(
                            SkippedEntity(entity_id=test_id, reason="missing_sample_id")
                        )
                        continue
                    if sample_id not in known_samples:
                        recovery_outcome: Optional[DependencyRecoveryOutcome] = None
                        if dependency_resolver:
                            recovery_outcome = attempt_dependency_recovery(
                                dependency_resolver,
                                "samples",
                                sample_id,
                                max_attempts=dependency_max_attempts,
                            )
                            if recovery_outcome.succeeded:
                                known_samples.add(sample_id)
                                summary.dependencies_recovered += 1

                        if sample_id not in known_samples:
                            summary.skipped_unknown_sample += 1
                            LOGGER.warning(
                                "Skipping test %s because sample %s does not exist locally%s",
                                item.get("id"),
                                sample_id,
                                ""
                                if not recovery_outcome or recovery_outcome.succeeded
                                else f" (recovery failed after {recovery_outcome.attempts} attempts)",
                            )
                            summary.skipped_entities.append(
                                SkippedEntity(
                                    entity_id=test_id,
                                    reason="unknown_sample",
                                    details={
                                        "sample_id": sample_id,
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

                    try:
                        enriched = _ensure_required_fields(client, item)
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == httpx.codes.BAD_REQUEST:
                            summary.detail_bad_request_failures += 1
                            summary.skipped_entities.append(
                                SkippedEntity(
                                    entity_id=test_id,
                                    reason="detail_bad_request",
                                    details={"status_code": exc.response.status_code},
                                )
                            )
                            LOGGER.warning(
                                "Skipping test %s due to repeated 400 BAD REQUEST when fetching detail",
                                item.get("id"),
                            )
                            continue
                        raise
                    if enriched is not item:
                        summary.detail_fetches += 1
                        item = enriched
                        time.sleep(DETAIL_SLEEP_SECONDS)

                    assay = item.get("assay") or {}
                    record = {
                        "id": item["id"],
                        "sample_id": sample_id,
                        "batch_ids": ensure_int_list(item.get("batches")),
                        "date_created": created_at,
                        "state": item.get("state"),
                        "has_report": bool(item.get("has_report", False)),
                        "report_completed_date": parse_qbench_datetime(item.get("report_completed_date")),
                        "label_abbr": item.get("label_abbr") or assay.get("label_abbr"),
                        "title": item.get("title") or assay.get("title"),
                        "worksheet_raw": item.get("worksheet_data") or item.get("worksheet_json") or item.get("worksheet_raw"),
                        "raw_payload": item,
                    }
                    records_to_upsert.append(record)
                    summary.processed += 1
                    if created_at and (max_synced_at is None or created_at > max_synced_at):
                        max_synced_at = created_at
                    if max_id is None or test_id > max_id:
                        max_id = test_id

                _persist_batch(records_to_upsert, current_page, max_synced_at, max_id, settings)
                if progress_callback:
                    progress_callback(summary.pages_seen, total_pages)

                if stop_after_page:
                    break
                # Continue processing all pages to ensure we get all new tests
                if total_pages and current_page >= total_pages:
                    break
                current_page += 1

    except Exception as exc:
        LOGGER.exception("Test sync failed on page %s", current_page)
        _mark_checkpoint_failed(current_page, settings, error=exc)
        raise

    _mark_checkpoint_completed(current_page, max_synced_at, max_id, settings)
    summary.last_synced_at = max_synced_at
    summary.last_id = max_id
    if summary.detail_bad_request_failures:
        LOGGER.warning(
            "Encountered %s tests that returned 400 BAD REQUEST on detail fetch and were skipped",
            summary.detail_bad_request_failures,
        )
    if summary.page_bad_request_failures:
        LOGGER.warning(
            "Encountered %s pages that returned 400 BAD REQUEST on list_tests and were skipped",
            summary.page_bad_request_failures,
        )
    return summary


def _ensure_required_fields(client: QBenchClient, item: dict) -> dict:
    """Fetch detail if required keys are missing."""

    assay = item.get("assay") or {}
    label = item.get("label_abbr") or assay.get("label_abbr")
    title = item.get("title") or assay.get("title")
    has_report_present = "has_report" in item
    report_present = "report_completed_date" in item
    worksheet_present = any(
        key in item and item.get(key) is not None
        for key in ("worksheet_data", "worksheet_json", "worksheet_raw")
    )

    if has_report_present and report_present and label and title and worksheet_present:
        return item

    detail = client.fetch_test(item["id"], include_raw_worksheet_data=True)
    if not detail:
        return item

    merged = dict(item)
    merged.update(detail)
    if "assay" not in merged and assay:
        merged["assay"] = assay
    if not merged.get("worksheet_data"):
        merged["worksheet_data"] = detail.get("worksheet_data") or detail.get("worksheet_json") or detail.get("worksheet_raw")
    return merged


def _persist_batch(
    rows: Iterable[dict],
    current_page: int,
    max_synced_at: Optional[datetime],
    max_id: Optional[int],
    settings: AppSettings,
) -> None:
    """Persist a batch of tests and update checkpoint progress."""

    with session_scope(settings) as session:
        checkpoint = _get_or_create_checkpoint(session)
        checkpoint.last_cursor = current_page
        checkpoint.status = "running"
        checkpoint.failed = False
        checkpoint.message = None

        if rows:
            insert_stmt = insert(Test).values(list(rows))
            update_stmt = {
                "sample_id": insert_stmt.excluded.sample_id,
                "batch_ids": insert_stmt.excluded.batch_ids,
                "date_created": insert_stmt.excluded.date_created,
                "state": insert_stmt.excluded.state,
                "has_report": insert_stmt.excluded.has_report,
                "report_completed_date": insert_stmt.excluded.report_completed_date,
                "label_abbr": insert_stmt.excluded.label_abbr,
                "title": insert_stmt.excluded.title,
                "worksheet_raw": insert_stmt.excluded.worksheet_raw,
                "raw_payload": insert_stmt.excluded.raw_payload,
                "fetched_at": func.now(),
            }
            session.execute(insert_stmt.on_conflict_do_update(index_elements=[Test.id], set_=update_stmt))
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


def _load_sample_ids(session: Session) -> set[int]:
    """Load all sample IDs present in the local database."""

    result = session.execute(select(Sample.id))
    return {row[0] for row in result}
