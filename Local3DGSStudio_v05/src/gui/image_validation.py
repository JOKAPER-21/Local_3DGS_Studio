"""Image Validation page: runs full dataset validation off the GUI
thread, shows live progress, a summary, a per-file table, and lets the
user export a report -- all read-only with respect to source files."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.image_validator import (
    STATUS_INVALID,
    STATUS_VALID,
    STATUS_WARNING,
    ImageValidationRecord,
    ImageValidationWorker,
    ValidationSummary,
)
from src.core.input_manager import InputManager
from src.core.logger import get_app_logger
from src.core.project_manager import ProjectManager
from src.utils.filesystem import human_readable_size

_STATUS_MESSAGES = {
    STATUS_VALID: "Dataset is ready for COLMAP.",
    STATUS_WARNING: "Dataset contains warnings.",
    STATUS_INVALID: "Dataset cannot be used until the errors are resolved.",
}

_STATUS_OBJECT_NAMES = {
    STATUS_VALID: "statusOk",
    STATUS_WARNING: "statusWarning",
    STATUS_INVALID: "statusError",
}


def _summary_card(title: str) -> tuple[QFrame, QLabel]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    heading = QLabel(title)
    heading.setObjectName("sectionLabel")
    value = QLabel("0")
    value.setStyleSheet("font-size: 18pt; font-weight: 600;")
    layout.addWidget(heading)
    layout.addWidget(value)
    return frame, value


class ImageValidationPage(QWidget):
    def __init__(self, project_manager: ProjectManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_manager = project_manager
        self.input_manager = InputManager(project_manager)
        self.logger = get_app_logger()
        self._worker: ImageValidationWorker | None = None
        self._records: list[ImageValidationRecord] = []
        self._summary: ValidationSummary | None = None

        outer = QVBoxLayout(self)
        title = QLabel("Image Validation")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        # -- summary cards -----------------------------------------------------
        grid = QGridLayout()
        grid.setSpacing(10)
        self.total_card, self.total_value = _summary_card("Total Images")
        self.valid_card, self.valid_value = _summary_card("Valid")
        self.warning_card, self.warning_value = _summary_card("Warnings")
        self.invalid_card, self.invalid_value = _summary_card("Invalid")
        self.duplicate_card, self.duplicate_value = _summary_card("Duplicates")
        self.size_card, self.size_value = _summary_card("Total Size")
        for column, card in enumerate(
            (
                self.total_card,
                self.valid_card,
                self.warning_card,
                self.invalid_card,
                self.duplicate_card,
                self.size_card,
            )
        ):
            grid.addWidget(card, 0, column)
        outer.addLayout(grid)

        # -- controls -----------------------------------------------------------
        controls = QHBoxLayout()
        self.validate_button = QPushButton("Validate Images")
        self.validate_button.clicked.connect(self._start_validation)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.clicked.connect(self._cancel_validation)
        self.cancel_button.setEnabled(False)
        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.refresh)
        open_folder_button = QPushButton("Open Image Folder")
        open_folder_button.setObjectName("secondaryButton")
        open_folder_button.clicked.connect(self._open_image_folder)
        export_button = QPushButton("Export Report")
        export_button.setObjectName("secondaryButton")
        export_button.clicked.connect(self._export_report)
        controls.addWidget(self.validate_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(refresh_button)
        controls.addWidget(open_folder_button)
        controls.addWidget(export_button)
        outer.addLayout(controls)

        # -- progress -------------------------------------------------------------
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_label = QLabel("")
        outer.addWidget(self.progress_bar)
        outer.addWidget(self.progress_label)

        # -- status banner ----------------------------------------------------------
        self.status_banner = QLabel("Run validation to see dataset status.")
        self.status_banner.setObjectName("statusMuted")
        outer.addWidget(self.status_banner)

        # -- table -------------------------------------------------------------------
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Filename", "Status", "Format", "Width", "Height", "File Size", "Issue"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        outer.addWidget(self.table, stretch=1)

        self.refresh()

    # -- helpers ------------------------------------------------------------------

    def refresh(self) -> None:
        if self.project_manager.current is None:
            self.status_banner.setObjectName("statusMuted")
            self.status_banner.setText("Open or create a project first.")
            return
        image_count = self.input_manager.count_images()
        self.total_value.setText(str(image_count))
        if image_count == 0:
            self.status_banner.setObjectName("statusWarning")
            self.status_banner.setText("No images found in the active image directory yet.")

    def _open_image_folder(self) -> None:
        path = self.input_manager.get_active_image_directory()
        if not path.is_dir():
            QMessageBox.warning(self, "Folder Not Found", f"This folder does not exist yet:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # -- validation run ------------------------------------------------------------

    def _start_validation(self) -> None:
        if self.project_manager.current is None:
            QMessageBox.warning(self, "No Project Open", "Open or create a project first.")
            return

        directory = self.input_manager.get_active_image_directory()
        if not directory.is_dir():
            QMessageBox.warning(
                self, "Image Directory Missing", f"This folder does not exist:\n{directory}"
            )
            return

        self.logger.info("Image validation started: %s", directory)
        self.validate_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting...")
        self.status_banner.setObjectName("statusMuted")
        self.status_banner.setText("Validation in progress...")

        self._worker = ImageValidationWorker(directory, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_result.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _cancel_validation(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.progress_label.setText("Cancelling...")

    def _on_progress(self, current: int, total: int, filename: str) -> None:
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.progress_label.setText(f"Validating {current} / {total}: {filename}")

    def _on_finished(self, records: list, summary: ValidationSummary) -> None:
        self.logger.info(
            "Image validation completed: %s total, status=%s",
            summary.total_images,
            summary.overall_status,
        )
        self._records = records
        self._summary = summary
        self.validate_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("Validation complete.")
        self._update_summary_cards(summary)
        self._update_table(records)
        self._update_status_banner(summary)
        self._persist_validation_result(summary)

    def _on_failed(self, message: str) -> None:
        self.logger.error("Image validation failed: %s", message)
        self.validate_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("Validation failed.")
        QMessageBox.critical(self, "Validation Error", message)

    def _update_summary_cards(self, summary: ValidationSummary) -> None:
        self.total_value.setText(str(summary.total_images))
        self.valid_value.setText(str(summary.valid_images))
        self.warning_value.setText(str(summary.warning_images))
        self.invalid_value.setText(str(summary.invalid_images))
        self.duplicate_value.setText(str(summary.duplicate_images))
        self.size_value.setText(human_readable_size(summary.total_size_bytes))

    def _update_table(self, records: list[ImageValidationRecord]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                record.filename,
                record.status,
                record.extension,
                str(record.width),
                str(record.height),
                human_readable_size(record.file_size_bytes),
                record.issue_summary,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)

    def _update_status_banner(self, summary: ValidationSummary) -> None:
        self.status_banner.setObjectName(_STATUS_OBJECT_NAMES[summary.overall_status])
        self.status_banner.setText(_STATUS_MESSAGES[summary.overall_status])
        self.status_banner.style().unpolish(self.status_banner)
        self.status_banner.style().polish(self.status_banner)

    def _persist_validation_result(self, summary: ValidationSummary) -> None:
        from datetime import datetime, timezone

        current = self.project_manager.current
        if current is None:
            return
        current.data.validation_info.update(
            {
                "lastValidationTime": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "validationStatus": summary.overall_status,
                "totalImages": summary.total_images,
                "validImages": summary.valid_images,
                "warningImages": summary.warning_images,
                "invalidImages": summary.invalid_images,
                "duplicateImages": summary.duplicate_images,
            }
        )
        self.project_manager.save_project_json()

    def _export_report(self) -> None:
        if self._summary is None:
            QMessageBox.information(self, "Nothing to Export", "Run validation first.")
            return

        default_name = "validation_report.json"
        current = self.project_manager.current
        default_dir = str(current.resolver.logs) if current is not None else ""
        target, _ = QFileDialog.getSaveFileName(
            self, "Export Validation Report", f"{default_dir}/{default_name}", "JSON (*.json)"
        )
        if not target:
            return

        report = {
            "summary": {
                "totalImages": self._summary.total_images,
                "validImages": self._summary.valid_images,
                "warningImages": self._summary.warning_images,
                "invalidImages": self._summary.invalid_images,
                "duplicateImages": self._summary.duplicate_images,
                "totalSize": self._summary.total_size_human,
                "commonResolution": self._summary.common_resolution,
                "status": self._summary.overall_status,
            },
            "files": [
                {
                    "filename": r.filename,
                    "status": r.status,
                    "extension": r.extension,
                    "width": r.width,
                    "height": r.height,
                    "fileSizeBytes": r.file_size_bytes,
                    "issues": r.issues,
                }
                for r in self._records
            ],
        }

        Path(target).write_text(json.dumps(report, indent=2), encoding="utf-8")
        QMessageBox.information(self, "Report Exported", f"Report saved to:\n{target}")
