#!/usr/bin/env python
"""Command-line entry point to synchronise all QBench entities sequentially."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from pprint import pformat

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.config import get_settings
from downloader_qbench_data.ingestion.pipeline import (
    DEFAULT_SYNC_SEQUENCE,
    SyncOrchestrationError,
    sync_all_entities,
)
from downloader_qbench_data.ingestion.utils import summarize_skipped_entities


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronise all QBench entities sequentially")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Perform a full refresh instead of incremental",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=None,
        help="Override page size (default 50, max 50)",
    )
    parser.add_argument(
        "--entity",
        dest="entities",
        action="append",
        choices=DEFAULT_SYNC_SEQUENCE,
        help="Limit the sync to a specific entity (can be repeated). Defaults to all.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    settings = get_settings()

    entity_sequence = args.entities or DEFAULT_SYNC_SEQUENCE
    logging.info("Starting multi-entity sync (entities=%s)", ", ".join(entity_sequence))

    disable_progress = not sys.stdout.isatty()
    entity_bar = tqdm(
        total=len(entity_sequence),
        unit="entity",
        desc="Entities",
        dynamic_ncols=True,
        disable=disable_progress,
    )

    current_page_bar: tqdm | None = None
    current_entity: str | None = None

    def _progress_callback(entity: str, processed_pages: int, total_pages: int | None) -> None:
        nonlocal current_page_bar, current_entity
        if disable_progress:
            return
        if current_entity != entity:
            if current_page_bar:
                current_page_bar.close()
            current_entity = entity
            current_page_bar = tqdm(
                total=total_pages or 0,
                unit="page",
                desc=f"{entity.title()}",
                dynamic_ncols=True,
                leave=False,
                disable=False,
            )
        if current_page_bar:
            if total_pages and current_page_bar.total != total_pages:
                current_page_bar.total = total_pages
            increment = processed_pages - current_page_bar.n
            if increment > 0:
                current_page_bar.update(increment)
            else:
                current_page_bar.refresh()

    try:
        summary = sync_all_entities(
            settings,
            entities=entity_sequence,
            full_refresh=args.full,
            page_size=args.page_size,
            progress_callback=_progress_callback if not disable_progress else None,
            raise_on_error=True,
        )
    except SyncOrchestrationError as exc:
        if current_page_bar:
            current_page_bar.close()
        entity_bar.close()
        logging.error("Sync failed: %s", exc)
        sys.exit(1)
    finally:
        if current_page_bar:
            current_page_bar.close()

    for result in summary.results:
        entity_bar.update(1)
    entity_bar.close()

    logging.info("Multi-entity sync completed successfully")
    for result in summary.results:
        logging.info(
            "Entity '%s' summary: %s",
            result.entity,
            pformat(getattr(result.summary, "__dict__", result.summary)),
        )
        skipped = getattr(result.summary, "skipped_entities", None) if result.summary else None
        if skipped:
            logging.warning("  Skipped entries (%d):", len(skipped))
            for line in summarize_skipped_entities(skipped):
                logging.warning("    %s", line)
        elif result.summary:
            logging.info("  No skipped entries for '%s'.", result.entity)


if __name__ == "__main__":
    main()
