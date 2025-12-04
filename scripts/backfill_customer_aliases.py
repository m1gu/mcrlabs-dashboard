#!/usr/bin/env python
"""Populate the aliases column with the current customer name as a starter value."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy import func, update

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.config import get_settings  # noqa: E402
from downloader_qbench_data.storage import Customer, session_scope  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()

    with session_scope(settings) as session:
        stmt = (
            update(Customer)
            .where(Customer.name.is_not(None))
            .where(func.coalesce(func.jsonb_array_length(Customer.aliases), 0) == 0)
            .values(aliases=func.jsonb_build_array(Customer.name))
        )
        result = session.execute(stmt)
        updated = result.rowcount or 0
        logging.info("Aliases iniciales asignados para %s clientes", updated)

    logging.info("Proceso completado")


if __name__ == "__main__":
    main()
