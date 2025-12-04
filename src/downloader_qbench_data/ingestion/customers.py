"""Ingestion routines for QBench customers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, Optional

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from downloader_qbench_data.clients.qbench import QBenchClient
from downloader_qbench_data.config import AppSettings, get_settings
from downloader_qbench_data.ingestion.recovery import EntityRecoveryService
from downloader_qbench_data.ingestion.utils import SkippedEntity, parse_qbench_datetime
from downloader_qbench_data.storage import Customer, SyncCheckpoint, session_scope

LOGGER = logging.getLogger(__name__)
ENTITY_NAME = "customers"
API_MAX_PAGE_SIZE = 50


@dataclass
class CustomerSyncSummary:
    """Aggregated statistics for a customer sync run."""

    processed: int = 0
    skipped_missing_name: int = 0
    skipped_old: int = 0
    pages_seen: int = 0
    last_synced_at: Optional[datetime] = None
    total_pages: Optional[int] = None
    start_page: int = 1
    skipped_entities: list[SkippedEntity] = field(default_factory=list)


def sync_customers(
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
) -> CustomerSyncSummary:
    """Synchronise customer data from QBench into PostgreSQL."""

    settings = settings or get_settings()
    effective_page_size = min(page_size or settings.page_size, API_MAX_PAGE_SIZE)
    _ = dependency_resolver, dependency_max_attempts  # parameters kept for signature parity

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

    summary = CustomerSyncSummary(last_synced_at=last_synced_at, start_page=start_page)
    baseline_synced_at = last_synced_at
    max_synced_at = last_synced_at
    max_id = last_id
    current_page = start_page

    try:
        with QBenchClient(
            base_url=settings.qbench.base_url,
            client_id=settings.qbench.client_id,
            client_secret=settings.qbench.client_secret,
            token_url=settings.qbench.token_url,
        ) as client:
            total_pages: Optional[int] = None
            while True:
                payload = client.list_customers(page_num=current_page, page_size=effective_page_size)
                total_pages = payload.get("total_pages") or total_pages
                summary.total_pages = total_pages
                customers = payload.get("data") or []
                if not customers:
                    break

                summary.pages_seen += 1
                records_to_upsert = []
                for item in customers:
                    name = item.get("customer_name") or item.get("name")
                    if not name:
                        summary.skipped_missing_name += 1
                        summary.skipped_entities.append(
                            SkippedEntity(entity_id=item.get("id"), reason="missing_name")
                        )
                        continue

                    customer_id = item["id"]
                    created_at = parse_qbench_datetime(item.get("date_created"))
                    if (
                        not full_refresh
                        and last_id is not None
                        and customer_id <= last_id
                    ):
                        summary.skipped_old += 1
                        continue

                    if start_datetime and created_at and created_at < start_datetime:
                        summary.skipped_old += 1
                        continue
                    if end_datetime and created_at and created_at > end_datetime:
                        continue

                    records_to_upsert.append(
                        {
                            "id": customer_id,
                            "name": name,
                            "aliases": [name],
                            "date_created": created_at,
                            "raw_payload": item,
                        }
                    )
                    summary.processed += 1
                    if created_at and (max_synced_at is None or created_at > max_synced_at):
                        max_synced_at = created_at
                    if max_id is None or customer_id > max_id:
                        max_id = customer_id

                _persist_batch(records_to_upsert, current_page, max_synced_at, max_id, settings)
                if progress_callback:
                    progress_callback(summary.pages_seen, total_pages)

                if total_pages and current_page >= total_pages:
                    break
                current_page += 1

    except Exception as exc:
        LOGGER.exception("Customer sync failed on page %s", current_page)
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
    """Persist a batch of customers and update checkpoint progress."""

    with session_scope(settings) as session:
        checkpoint = _get_or_create_checkpoint(session)
        checkpoint.last_cursor = current_page
        checkpoint.status = "running"
        checkpoint.failed = False
        checkpoint.message = None

        if rows:
            insert_stmt = insert(Customer).values(list(rows))
            update_stmt = {
                "name": insert_stmt.excluded.name,
                "date_created": insert_stmt.excluded.date_created,
                "raw_payload": insert_stmt.excluded.raw_payload,
            }
            update_stmt["fetched_at"] = func.now()
            session.execute(insert_stmt.on_conflict_do_update(index_elements=[Customer.id], set_=update_stmt))
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
    """Fetch existing checkpoint or create one."""

    checkpoint = session.get(SyncCheckpoint, ENTITY_NAME)
    if not checkpoint:
        checkpoint = SyncCheckpoint(entity=ENTITY_NAME, status="never", failed=False)
        session.add(checkpoint)
        session.flush()
    return checkpoint
