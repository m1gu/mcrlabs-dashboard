#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.ui.dashboard import DashboardConfig, DashboardWindow  # noqa: E402


def main() -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    window = DashboardWindow(config=DashboardConfig())
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

