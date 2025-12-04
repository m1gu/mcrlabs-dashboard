#!/usr/bin/env python
"""Launch the Downloader QBench Data API using uvicorn."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.api import create_app  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Downloader QBench Data API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface")
    parser.add_argument("--port", type=int, default=8000, help="TCP port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (development only)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        "downloader_qbench_data.api.main:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
