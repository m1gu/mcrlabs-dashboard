"""Helpers to recover QBench entities (and dependencies) on demand."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from downloader_qbench_data.clients.qbench import QBenchClient
from downloader_qbench_data.config import AppSettings, get_settings
from downloader_qbench_data.ingestion.utils import (
    ensure_int_list,
    parse_qbench_datetime,
    safe_decimal,
    safe_int,
)
from downloader_qbench_data.storage import (
    Batch,
    Customer,
    Order,
    Sample,
    SyncCheckpoint,
    Test,
    session_scope,
)

LOGGER = logging.getLogger(__name__)

EntityId = int | str

ENTITY_ALIASES: dict[str, str] = {
    "customer": "customers",
    "customers": "customers",
    "order": "orders",
    "orders": "orders",
    "sample": "samples",
    "samples": "samples",
    "batch": "batches",
    "batches": "batches",
    "test": "tests",
    "tests": "tests",
}

ENTITY_MODELS = {
    "customers": Customer,
    "orders": Order,
    "samples": Sample,
    "batches": Batch,
    "tests": Test,
}


@dataclass
class EnsureResult:
    """Represents the outcome of a recovery attempt."""

    succeeded: bool
    error: Optional[str] = None


class RecoveryError(RuntimeError):
    """Raised when recovery of an entity fails."""


class EntityRecoveryService:
    """Fetches and persists missing entities while ensuring dependencies."""

    def __init__(self, settings: Optional[AppSettings] = None, client: Optional[QBenchClient] = None) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = False
        if self._client is None:
            self._client = QBenchClient(
                base_url=self.settings.qbench.base_url,
                client_id=self.settings.qbench.client_id,
                client_secret=self.settings.qbench.client_secret,
                token_url=self.settings.qbench.token_url,
            )
            self._owns_client = True

    @property
    def client(self) -> QBenchClient:
        assert self._client is not None
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    def ensure(self, entity_type: str, entity_id: EntityId) -> EnsureResult:
        """Ensure the provided entity exists locally, fetching it (and dependencies) if required."""

        normalised = ENTITY_ALIASES.get(entity_type)
        if not normalised:
            return EnsureResult(False, f"unsupported_entity:{entity_type}")

        try:
            self._recover(normalised, entity_id, visited=set())
            return EnsureResult(True)
        except RecoveryError as exc:
            LOGGER.warning("Recovery failed for %s %s: %s", normalised, entity_id, exc)
            return EnsureResult(False, str(exc))

    def _recover(self, entity_type: str, entity_id: EntityId, *, visited: set[Tuple[str, EntityId]]) -> None:
        key = (entity_type, entity_id)
        if key in visited:
            raise RecoveryError(f"cyclic_dependency:{entity_type}:{entity_id}")
        visited.add(key)

        if self._exists(entity_type, entity_id):
            LOGGER.debug("Entity %s %s already exists locally; skipping recovery", entity_type, entity_id)
            return

        data = self._fetch(entity_type, entity_id)
        if not data:
            raise RecoveryError(f"not_found_remote:{entity_type}:{entity_id}")

        record = _transform_record(entity_type, data)
        dependency_pairs = _extract_dependencies(entity_type, record)
        for dependency_type, dependency_id in dependency_pairs:
            if dependency_id is None:
                raise RecoveryError(f"missing_dependency_id:{dependency_type}:{entity_type}:{entity_id}")
            self._recover(dependency_type, dependency_id, visited=visited)

        _persist_record(entity_type, record, self.settings)

    def _exists(self, entity_type: str, entity_id: EntityId) -> bool:
        model = ENTITY_MODELS[entity_type]
        with session_scope(self.settings) as session:
            stmt = select(model.id).where(model.id == entity_id)
            return session.execute(stmt).first() is not None

    def _fetch(self, entity_type: str, entity_id: EntityId) -> Optional[Dict[str, Any]]:
        client = self.client
        if entity_type == "customers":
            return client.fetch_customer(entity_id)
        if entity_type == "orders":
            return client.fetch_order(entity_id)
        if entity_type == "samples":
            return client.fetch_sample(entity_id)
        if entity_type == "batches":
            return client.fetch_batch(entity_id, include_raw_worksheet_data=True)
        if entity_type == "tests":
            return client.fetch_test(entity_id, include_raw_worksheet_data=True)
        raise RecoveryError(f"unsupported_entity:{entity_type}")


def _transform_record(entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if entity_type == "customers":
        return {
            "id": data["id"],
            "name": data.get("customer_name") or data.get("name"),
            "date_created": parse_qbench_datetime(data.get("date_created")),
            "raw_payload": data,
        }
    if entity_type == "orders":
        return {
            "id": data["id"],
            "custom_formatted_id": data.get("custom_formatted_id"),
            "customer_account_id": data.get("customer_account_id"),
            "date_created": parse_qbench_datetime(data.get("date_created")),
            "date_completed": parse_qbench_datetime(data.get("date_completed")),
            "date_order_reported": parse_qbench_datetime(data.get("date_order_reported")),
            "date_received": parse_qbench_datetime(data.get("date_received")),
            "sample_count": safe_int(data.get("sample_count")),
            "test_count": safe_int(data.get("test_count")),
            "state": data.get("state"),
            "raw_payload": data,
        }
    if entity_type == "samples":
        return {
            "id": data["id"],
            "sample_name": data.get("sample_name") or data.get("description"),
            "custom_formatted_id": data.get("custom_formatted_id"),
            "order_id": data.get("order_id"),
            "has_report": bool(data.get("has_report")),
            "batch_ids": ensure_int_list(data.get("batches") or data.get("batch_ids")),
            "completed_date": parse_qbench_datetime(data.get("completed_date") or data.get("complete_date")),
            "date_created": parse_qbench_datetime(data.get("date_created")),
            "start_date": parse_qbench_datetime(data.get("start_date")),
            "matrix_type": data.get("matrix_type"),
            "state": data.get("state"),
            "test_count": safe_int(data.get("test_count")),
            "sample_weight": safe_decimal(data.get("sample_weight")),
            "raw_payload": data,
        }
    if entity_type == "batches":
        return {
            "id": data["id"],
            "assay_id": data.get("assay_id"),
            "display_name": data.get("display_name"),
            "date_created": parse_qbench_datetime(data.get("date_created")),
            "date_prepared": parse_qbench_datetime(data.get("date_prepared")),
            "last_updated": parse_qbench_datetime(data.get("last_updated")),
            "sample_ids": ensure_int_list(data.get("sample_ids")),
            "test_ids": ensure_int_list(data.get("test_ids")),
            "raw_payload": data,
        }
    if entity_type == "tests":
        assay = data.get("assay") or {}
        return {
            "id": data["id"],
            "sample_id": data.get("sample_id"),
            "batch_ids": ensure_int_list(data.get("batches") or data.get("batch_ids")),
            "date_created": parse_qbench_datetime(data.get("date_created")),
            "state": data.get("state"),
            "has_report": bool(data.get("has_report", False)),
            "report_completed_date": parse_qbench_datetime(data.get("report_completed_date")),
            "label_abbr": data.get("label_abbr") or assay.get("label_abbr"),
            "title": data.get("title") or assay.get("title"),
            "worksheet_raw": data.get("worksheet_data") or data.get("worksheet_json") or data.get("worksheet_raw"),
            "raw_payload": data,
        }
    raise RecoveryError(f"unsupported_entity:{entity_type}")


def _extract_dependencies(entity_type: str, record: Dict[str, Any]) -> Sequence[Tuple[str, EntityId]]:
    if entity_type == "orders":
        return [("customers", record.get("customer_account_id"))]
    if entity_type == "samples":
        return [("orders", record.get("order_id"))]
    if entity_type == "tests":
        return [("samples", record.get("sample_id"))]
    return []


def _persist_record(entity_type: str, record: Dict[str, Any], settings: AppSettings) -> None:
    model = ENTITY_MODELS[entity_type]
    values = dict(record)

    upsert_fields = {
        "customers": ("name", "date_created", "raw_payload"),
        "orders": (
            "custom_formatted_id",
            "customer_account_id",
            "date_created",
            "date_completed",
            "date_order_reported",
            "date_received",
            "sample_count",
            "test_count",
            "state",
            "raw_payload",
        ),
        "samples": (
            "sample_name",
            "custom_formatted_id",
            "order_id",
            "has_report",
            "batch_ids",
            "completed_date",
            "date_created",
            "start_date",
            "matrix_type",
            "state",
            "test_count",
            "sample_weight",
            "raw_payload",
        ),
        "batches": (
            "assay_id",
            "display_name",
            "date_created",
            "date_prepared",
            "last_updated",
            "sample_ids",
            "test_ids",
            "raw_payload",
        ),
        "tests": (
            "sample_id",
            "batch_ids",
            "date_created",
            "state",
            "has_report",
            "report_completed_date",
            "label_abbr",
            "title",
            "worksheet_raw",
            "raw_payload",
        ),
    }[entity_type]

    with session_scope(settings) as session:
        insert_stmt = insert(model).values(values)
        update_stmt = {field: insert_stmt.excluded[field] for field in upsert_fields}
        update_stmt["fetched_at"] = func.now()
        session.execute(insert_stmt.on_conflict_do_update(index_elements=[model.id], set_=update_stmt))
        _update_checkpoint(session, entity_type, record)


def _update_checkpoint(session, entity_type: str, record: Dict[str, Any]) -> None:
    checkpoint = session.get(SyncCheckpoint, entity_type)
    if not checkpoint:
        checkpoint = SyncCheckpoint(entity=entity_type, status="never", failed=False)
        session.add(checkpoint)
        session.flush()

    entity_id = record.get("id")
    if entity_id is None:
        return

    if checkpoint.last_id is None or entity_id > checkpoint.last_id:
        checkpoint.last_id = entity_id
        checkpoint.last_synced_at = record.get("date_created") or record.get("fetched_at")
    checkpoint.status = "completed"
    checkpoint.failed = False
    checkpoint.message = "Recovered on demand"


@dataclass
class DependencyRecoveryOutcome:
    """Summary for a dependency recovery loop."""

    succeeded: bool
    attempts: int
    error: Optional[str] = None


def attempt_dependency_recovery(
    resolver: EntityRecoveryService,
    entity_type: str,
    entity_id: EntityId,
    *,
    max_attempts: int,
) -> DependencyRecoveryOutcome:
    attempts = 0
    last_error: Optional[str] = None

    while attempts < max_attempts:
        attempts += 1
        result = resolver.ensure(entity_type, entity_id)
        if result.succeeded:
            return DependencyRecoveryOutcome(True, attempts, None)
        last_error = result.error

    return DependencyRecoveryOutcome(False, attempts, last_error)
