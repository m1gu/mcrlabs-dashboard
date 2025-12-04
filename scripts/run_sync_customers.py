#!/usr/bin/env python
"""Command-line entry point to synchronise QBench customers."""

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
from downloader_qbench_data.ingestion.customers import sync_customers
from downloader_qbench_data.ingestion.utils import summarize_skipped_entities


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronise QBench customers")
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
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    settings = get_settings()
    logging.info("Starting customer sync (full_refresh=%s)", args.full)
    disable_progress = not sys.stdout.isatty()
    with tqdm(
        total=None,
        unit="page",
        desc="Customers",
        dynamic_ncols=True,
        disable=disable_progress,
    ) as progress_bar:

        def progress_callback(processed_pages: int, total_pages: int | None) -> None:
            if total_pages and progress_bar.total != total_pages:
                progress_bar.total = total_pages
            increment = processed_pages - progress_bar.n
            if increment > 0:
                progress_bar.update(increment)
            else:
                progress_bar.refresh()

        summary = sync_customers(
            settings,
            full_refresh=args.full,
            page_size=args.page_size,
            progress_callback=progress_callback,
        )
    if disable_progress:
        logging.info("Processed %s pages", summary.pages_seen)
    logging.info("Customer sync completed: %s", pformat(summary.__dict__))
    if summary.skipped_entities:
        logging.warning("Customers skipped (%d):", len(summary.skipped_entities))
        for line in summarize_skipped_entities(summary.skipped_entities):
            logging.warning("  %s", line)
    else:
        logging.info("No customers were skipped during the sync.")


if __name__ == "__main__":
    main()
