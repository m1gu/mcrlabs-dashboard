#!/usr/bin/env python3
"""Fetch and persist QBench entities by ID with automatic dependency recovery."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.config import get_settings
from downloader_qbench_data.ingestion.recovery import ENTITY_ALIASES, EntityRecoveryService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
LOGGER = logging.getLogger(__name__)

ENTITY_CHOICES = sorted(set(ENTITY_ALIASES.keys()))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga y guarda entidades QBench por ID, recuperando dependencias faltantes."
    )
    parser.add_argument("entity_type", choices=ENTITY_CHOICES, help="Tipo de entidad a recuperar (singular o plural)")
    parser.add_argument(
        "entity_ids",
        nargs="+",
        help="IDs de las entidades a procesar (separados por espacio)",
    )
    parser.add_argument(
        "--skip-foreign-check",
        action="store_true",
        help=argparse.SUPPRESS,  # mantenido por compatibilidad; la recuperación valida dependencias automáticamente
    )

    args = parser.parse_args()
    settings = get_settings()
    normalised_type = ENTITY_ALIASES[args.entity_type]

    success_count = 0
    total_count = len(args.entity_ids)

    service = EntityRecoveryService(settings=settings)
    try:
        for index, entity_id in enumerate(args.entity_ids, start=1):
            LOGGER.info("Procesando %s %s (%s/%s)", normalised_type.rstrip("s"), entity_id, index, total_count)
            result = service.ensure(normalised_type, entity_id)
            if result.succeeded:
                success_count += 1
                LOGGER.info("✓ Recuperado %s %s", normalised_type.rstrip("s"), entity_id)
            else:
                LOGGER.error("✗ No se pudo recuperar %s %s (%s)", normalised_type.rstrip("s"), entity_id, result.error)
    finally:
        service.close()

    LOGGER.info("Recuperación completada: %s/%s exitosas", success_count, total_count)
    if success_count != total_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
