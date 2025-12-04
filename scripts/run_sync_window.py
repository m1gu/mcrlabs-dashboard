#!/usr/bin/env python
"""Execute the windowed sync pipeline and persist a skip report."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.config import get_settings
from downloader_qbench_data.ingestion.pipeline import (
    DEFAULT_SYNC_SEQUENCE,
    collect_skipped_entities,
    sync_recent_entities,
)

LOGGER = logging.getLogger(__name__)
REPORT_DIR = PROJECT_ROOT / "docs" / "sync_reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the windowed sync pipeline and generate a skip report.")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Number of days to look back from today (defaults to SYNC_LOOKBACK_DAYS).",
    )
    parser.add_argument(
        "--entity",
        dest="entities",
        action="append",
        choices=DEFAULT_SYNC_SEQUENCE,
        help="Limit the sync to a subset of entities (can be provided multiple times).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=None,
        help="Optional page size override passed to each entity pipeline.",
    )
    parser.add_argument(
        "--dependency-attempts",
        type=int,
        default=3,
        help="Maximum dependency recovery attempts per entity (default: 3).",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=REPORT_DIR,
        help="Directory where the TXT report will be stored (default: docs/sync_reports).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO).",
    )
    return parser.parse_args()


def dedupe_entity_ids(values: Iterable[object]) -> List[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value is None:
            continue
        identifier = str(value)
        if identifier not in seen:
            seen.add(identifier)
            ordered.append(identifier)
    return ordered


def collect_processed_counts(summary) -> Dict[str, Optional[int]]:
    counts: dict[str, Optional[int]] = {}
    for result in summary.results:
        processed = getattr(result.summary, "processed", None) if result.summary else None
        counts[result.entity] = processed
    return counts


def write_report(
    report_path: Path,
    run_date: datetime,
    skipped_map: dict[str, list],
    processed_map: dict[str, Optional[int]],
) -> None:
    lines = [
        f"Fecha de la actualizacion: {run_date.date().isoformat()}",
        "Items skipped",
    ]
    for entity in DEFAULT_SYNC_SEQUENCE:
        entries = skipped_map.get(entity, [])
        entity_ids = dedupe_entity_ids(entry.entity_id for entry in entries)
        joined = " ".join(entity_ids)
        processed = processed_map.get(entity)
        processed_str = processed if processed is not None else "NA"
        lines.append(f"{entity}: nuevos={processed_str} skipped=[{joined}]")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    LOGGER.info("Reporte generado en %s", report_path)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = get_settings()
    run_date = datetime.utcnow()

    LOGGER.info("Iniciando ventana de sincronizacion (fecha=%s)", run_date.isoformat())
    summary = sync_recent_entities(
        settings,
        lookback_days=args.days,
        entities=args.entities,
        page_size=args.page_size,
        dependency_max_attempts=args.dependency_attempts,
        raise_on_error=False,
    )

    if summary.succeeded:
        LOGGER.info("Windowed sync finished successfully in %.2f seconds", summary.total_duration_seconds)
    else:
        LOGGER.warning(
            "Windowed sync completed with failures (failed_entity=%s, error=%s)",
            summary.failed_entity,
            summary.error_message,
        )

    skipped_map = collect_skipped_entities(summary)
    processed_map = collect_processed_counts(summary)

    for entity, skipped in skipped_map.items():
        if not skipped:
            LOGGER.info(
                "Entity '%s': %s nuevos registros, no skipped items.",
                entity,
                processed_map.get(entity),
            )
            continue
        LOGGER.warning(
            "Entity '%s': %s nuevos registros, %s skipped items.",
            entity,
            processed_map.get(entity),
            len(skipped),
        )
        for item in skipped:
            LOGGER.warning("  id=%s reason=%s details=%s", item.entity_id, item.reason, item.details)

    report_name = f"sync_report_{run_date.date().isoformat()}.txt"
    report_path = (args.report_dir or REPORT_DIR) / report_name
    write_report(report_path, run_date, skipped_map, processed_map)

    if not summary.succeeded:
        sys.exit(1)


if __name__ == "__main__":
    main()
