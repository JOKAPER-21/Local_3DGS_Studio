"""Entry point for Local 3DGS Studio."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from src.core.logger import get_app_logger
from src.gui.main_window import MainWindow
from src.gui.theme import DARK_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local3DGSStudio")
    app.setStyleSheet(DARK_STYLESHEET)

    logger = get_app_logger()
    logger.info("Starting Local 3DGS Studio")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
