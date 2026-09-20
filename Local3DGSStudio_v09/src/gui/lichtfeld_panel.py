"""LichtFeld workspace page.

Everything here reuses existing core logic:
``software_detector.detect_software`` for the executable, the persisted
``reconstructionQC`` section (via ``QCResult.from_project_json_dict``)
for reconstruction status, and ``LichtFeldManager`` for both actions
("Prepare Scene" and "Open in LichtFeld"). This page performs no staging,
no launching, and no QC arithmetic of its own -- it only calls into
those and renders the result, matching the pattern already established
by ``reconstruction_qc_panel.py`` (no blocking ``QMessageBox`` calls, so
this page stays safe to drive from headless/automated tests).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.config_manager import ConfigManager
from src.core.lichtfeld_config import LichtFeldConfig
from src.core.lichtfeld_manager import LichtFeldManager
from src.core.project_manager import ProjectManager
from src.core.reconstruction_qc import QCResult
from src.core.software_detector import detect_software


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    heading = QLabel(title)
    heading.setObjectName("sectionLabel")
    layout.addWidget(heading)
    return frame, layout


def _stat_row(label_text: str) -> tuple[QWidget, QLabel]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    caption = QLabel(label_text)
    value = QLabel("--")
    value.setStyleSheet("font-weight: 600;")
    layout.addWidget(caption)
    layout.addStretch(1)
    layout.addWidget(value)
    return row, value


class LichtFeldPage(QWidget):
    def __init__(
        self,
        project_manager: ProjectManager,
        config_manager: ConfigManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_manager = project_manager
        self.config_manager = config_manager or ConfigManager()

        outer = QVBoxLayout(self)
        title = QLabel("LichtFeld")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        status_card, status_layout = _card("Status")
        row, self.executable_value = _stat_row("LichtFeld Executable")
        status_layout.addWidget(row)
        row, self.reconstruction_value = _stat_row("COLMAP Reconstruction")
        status_layout.addWidget(row)
        row, self.image_source_value = _stat_row("Image Source")
        status_layout.addWidget(row)
        row, self.staging_value = _stat_row("Temporary Staging")
        status_layout.addWidget(row)
        outer.addWidget(status_card)

        actions = QHBoxLayout()
        self.prepare_button = QPushButton("Prepare Scene")
        self.prepare_button.setObjectName("secondaryButton")
        self.prepare_button.clicked.connect(self._on_prepare_scene)
        self.open_button = QPushButton("Open in LichtFeld")
        self.open_button.clicked.connect(self._on_open_in_lichtfeld)
        actions.addWidget(self.prepare_button)
        actions.addWidget(self.open_button)
        actions.addStretch(1)
        outer.addLayout(actions)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        outer.addWidget(self.result_label)

        outer.addStretch(1)
        self.refresh()

    def _manager(self) -> LichtFeldManager:
        settings = self.config_manager.load_settings()
        config = LichtFeldConfig(executable_path=settings.external_software.lichtfeld)
        return LichtFeldManager(self.project_manager, config)

    def _current_qc_result(self) -> QCResult:
        current = self.project_manager.current
        if current is None:
            return QCResult()
        return QCResult.from_project_json_dict(current.data.reconstruction_qc_info)

    def refresh(self) -> None:
        current = self.project_manager.current
        if current is None:
            self.executable_value.setText("--")
            self.reconstruction_value.setText("--")
            self.image_source_value.setText("--")
            self.staging_value.setText("--")
            self.prepare_button.setEnabled(False)
            self.open_button.setEnabled(False)
            return

        settings = self.config_manager.load_settings()
        detection = detect_software("lichtfeld", settings.external_software.lichtfeld)
        self.executable_value.setText(
            f"Detected ({detection.path})" if detection.found else "Not detected"
        )

        qc_result = self._current_qc_result()
        self.reconstruction_value.setText(qc_result.state)
        self.image_source_value.setText(str(current.resolver.images))
        self.staging_value.setText("Not prepared yet")

        eligible = qc_result.is_ready_for_lichtfeld
        self.prepare_button.setEnabled(eligible)
        self.open_button.setEnabled(eligible)

    def _on_prepare_scene(self) -> None:
        manager = self._manager()
        result = manager.prepare_scene(self._current_qc_result())
        if result.success:
            self.staging_value.setText(str(result.staging.staging_root) if result.staging else "n/a")
            self.result_label.setObjectName("statusOk")
            self.result_label.setText("Scene staged successfully.")
        else:
            self.result_label.setObjectName("statusError")
            self.result_label.setText(f"Prepare Scene failed: {result.error}")
        self._repolish_result_label()

    def _on_open_in_lichtfeld(self) -> None:
        manager = self._manager()
        result = manager.send_to_lichtfeld(self._current_qc_result())
        if result.success:
            self.staging_value.setText(str(result.staging.staging_root) if result.staging else "n/a")
            self.result_label.setObjectName("statusOk")
            self.result_label.setText(f"LichtFeld Studio started (PID {result.pid}).")
        else:
            self.result_label.setObjectName("statusError")
            self.result_label.setText(f"Open in LichtFeld failed: {result.error}")
        self._repolish_result_label()

    def _repolish_result_label(self) -> None:
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
