"""Logs page: shows live console output and lets the user pick a project
log file to tail (application.log, colmap.log, lichtfeld.log, render.log)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.project_manager import ProjectManager

_LOG_FILE_CHOICES = ["application.log", "colmap.log", "lichtfeld.log", "training.log", "render.log"]


class LogsPage(QWidget):
    def __init__(self, project_manager: ProjectManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_manager = project_manager
        self._last_read_size = 0

        outer = QVBoxLayout(self)
        title = QLabel("Logs")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        controls = QHBoxLayout()
        self.log_selector = QComboBox()
        self.log_selector.addItems(_LOG_FILE_CHOICES)
        self.log_selector.currentIndexChanged.connect(self._reload)
        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self._reload)
        clear_button = QPushButton("Clear View")
        clear_button.setObjectName("secondaryButton")
        clear_button.clicked.connect(lambda: self.log_view.clear())
        controls.addWidget(QLabel("Log file:"))
        controls.addWidget(self.log_selector)
        controls.addWidget(refresh_button)
        controls.addWidget(clear_button)
        controls.addStretch(1)
        outer.addLayout(controls)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        outer.addWidget(self.log_view)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        self._reload()

    def _current_log_path(self) -> Path | None:
        current = self.project_manager.current
        if current is None:
            return None
        filename = self.log_selector.currentText()
        return current.resolver.logs / filename

    def _reload(self) -> None:
        self.log_view.clear()
        self._last_read_size = 0
        path = self._current_log_path()
        if path is None:
            self.log_view.setPlainText("(no project open)")
            return
        if not path.exists():
            self.log_view.setPlainText(f"(log file not yet created: {path})")
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        self.log_view.setPlainText(text)
        self._last_read_size = path.stat().st_size
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def _poll(self) -> None:
        path = self._current_log_path()
        if path is None or not path.exists():
            return
        size = path.stat().st_size
        if size < self._last_read_size:
            # File was truncated/rotated -- reload from scratch.
            self._reload()
            return
        if size == self._last_read_size:
            return
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self._last_read_size)
            new_text = handle.read()
        self._last_read_size = size
        self.log_view.appendPlainText(new_text.rstrip("\n"))
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
