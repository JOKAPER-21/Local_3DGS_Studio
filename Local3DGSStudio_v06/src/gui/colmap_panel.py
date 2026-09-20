"""COLMAP page: detection, preflight, the five-stage pipeline (Database,
Feature Extraction, Feature Matching, Mapper, Model Analysis), live
command preview + logs, cancellation, and reconstruction metrics --
built entirely on the existing ``ManagedProcess``/``QProcess`` wrapper so
the GUI thread is never blocked.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices, QClipboard
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QComboBox,
    QVBoxLayout,
    QWidget,
)

from src.core.colmap_config import COLMAPConfig
from src.core.colmap_manager import (
    COLMAPManager,
    ColmapCommand,
    ColmapDetectionResult,
    DatabaseExistsError,
    SparseModelExistsError,
    detect_colmap_executable,
)
from src.core.colmap_runner import start_colmap_command
from src.core.config_manager import ConfigManager
from src.core.logger import get_app_logger
from src.core.process_manager import ManagedProcess, ProcessResult
from src.core.project_manager import ProjectLoadError, ProjectManager
from src.gui.colmap_pipeline_widget import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
    ColmapPipelineWidget,
)
from src.gui.colmap_settings import ColmapSettingsWidget
from src.utils.colmap_parser import calculate_registration_percentage, parse_model_analyzer_output

_STEP_ORDER = ["Database", "Features", "Matching", "Mapper", "Analysis"]


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    heading = QLabel(title)
    heading.setObjectName("sectionLabel")
    layout.addWidget(heading)
    return frame, layout


class ColmapPanel(QWidget):
    # Emitted whenever the full pipeline (or a single step) finishes,
    # successfully or not, so other pages (Reconstruction QC) can
    # refresh -- kept as a signal rather than a direct call so this
    # module never has to know about ReconstructionQC, per the "no QC
    # calculations in colmap_panel.py" architecture rule.
    pipeline_finished = Signal()

    def __init__(
        self,
        project_manager: ProjectManager,
        config_manager: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_manager = project_manager
        self.config_manager = config_manager
        self.logger = get_app_logger()

        self.manager = COLMAPManager(project_manager)
        self._detection: ColmapDetectionResult | None = None
        self._process: ManagedProcess | None = None
        self._pending_steps: list[str] = []
        self._running_full_pipeline = False
        self._current_step: str | None = None
        self._cancel_requested = False

        outer = QVBoxLayout(self)
        title = QLabel("COLMAP")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        # -- COLMAP status card --------------------------------------------------
        status_card, status_layout = _card("COLMAP Status")

        path_row = QHBoxLayout()
        self.colmap_path_edit = QLineEdit()
        browse_button = QPushButton("Browse...")
        browse_button.setObjectName("secondaryButton")
        browse_button.clicked.connect(self._browse_colmap)
        detect_button = QPushButton("Detect COLMAP")
        detect_button.setObjectName("secondaryButton")
        detect_button.clicked.connect(self._detect_colmap)
        path_row.addWidget(self.colmap_path_edit)
        path_row.addWidget(browse_button)
        path_row.addWidget(detect_button)
        status_layout.addLayout(path_row)

        self.colmap_version_label = QLabel("Version: not detected")
        self.detection_status_label = QLabel("Detection status: not detected")
        self.active_project_label = QLabel("")
        self.active_version_label = QLabel("")
        for label in (
            self.colmap_version_label,
            self.detection_status_label,
            self.active_project_label,
            self.active_version_label,
        ):
            label.setWordWrap(True)
            status_layout.addWidget(label)
        outer.addWidget(status_card)

        # -- input card ------------------------------------------------------------
        input_card, input_layout = _card("Input")
        self.image_folder_label = QLabel("")
        self.image_count_label = QLabel("")
        self.validation_status_label = QLabel("")
        for label in (self.image_folder_label, self.image_count_label, self.validation_status_label):
            label.setWordWrap(True)
            input_layout.addWidget(label)
        input_buttons = QHBoxLayout()
        open_image_folder_button = QPushButton("Open Image Folder")
        open_image_folder_button.setObjectName("secondaryButton")
        open_image_folder_button.clicked.connect(self._open_image_folder)
        input_buttons.addWidget(open_image_folder_button)
        input_layout.addLayout(input_buttons)
        outer.addWidget(input_card)

        # -- settings card -----------------------------------------------------------
        settings_card, settings_layout = _card("Feature Extraction / Matching Settings")
        self.settings_widget = ColmapSettingsWidget(self.manager.config)
        settings_layout.addWidget(self.settings_widget)
        outer.addWidget(settings_card)

        # -- pipeline status ---------------------------------------------------------
        outer.addWidget(self._label("COLMAP Pipeline"))
        self.pipeline_widget = ColmapPipelineWidget()
        outer.addWidget(self.pipeline_widget)

        # -- controls ------------------------------------------------------------------
        controls = QHBoxLayout()
        self.run_full_button = QPushButton("Run Full COLMAP Pipeline")
        self.run_full_button.clicked.connect(self._on_run_full_pipeline)
        self.step_selector = QComboBox()
        self.step_selector.addItems(_STEP_ORDER)
        self.run_step_button = QPushButton("Run Selected Step")
        self.run_step_button.setObjectName("secondaryButton")
        self.run_step_button.clicked.connect(self._on_run_selected_step)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("secondaryButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        refresh_button = QPushButton("Refresh Status")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.run_full_button)
        controls.addWidget(self.step_selector)
        controls.addWidget(self.run_step_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(refresh_button)
        outer.addLayout(controls)

        # -- command preview -------------------------------------------------------------
        preview_row = QHBoxLayout()
        self.command_preview_label = QLabel("(no command run yet)")
        self.command_preview_label.setWordWrap(True)
        copy_command_button = QPushButton("Copy Command")
        copy_command_button.setObjectName("secondaryButton")
        copy_command_button.clicked.connect(self._copy_command_to_clipboard)
        preview_row.addWidget(self.command_preview_label, stretch=1)
        preview_row.addWidget(copy_command_button)
        outer.addLayout(preview_row)

        # -- metrics ----------------------------------------------------------------------
        self.metrics_label = QLabel("")
        self.metrics_label.setWordWrap(True)
        outer.addWidget(self.metrics_label)

        # -- live log ------------------------------------------------------------------------
        outer.addWidget(self._label("Live Output"))
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        outer.addWidget(self.log_view, stretch=1)

        self._load_default_colmap_path()
        self.refresh()

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    # -- setup / detection ---------------------------------------------------------------

    def _load_default_colmap_path(self) -> None:
        settings = self.config_manager.load_settings()
        self.colmap_path_edit.setText(settings.external_software.colmap)
        self.manager.config.executable_path = settings.external_software.colmap

    def _browse_colmap(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select COLMAP Executable")
        if not path:
            return
        self.colmap_path_edit.setText(path)
        settings = self.config_manager.load_settings()
        settings.external_software.colmap = path
        self.config_manager.save_settings(settings)
        self._detect_colmap()

    def _detect_colmap(self) -> None:
        path = self.colmap_path_edit.text().strip()
        self.logger.info("COLMAP detection started: %s", path)
        self._detection = detect_colmap_executable(path)
        self.manager.config.executable_path = path
        if self._detection.detected:
            cuda_note = " (CUDA build)" if self._detection.cuda_build else ""
            self.colmap_version_label.setText(f"Version: {self._detection.version}{cuda_note}")
            self.detection_status_label.setObjectName("statusOk")
            self.detection_status_label.setText("Detection status: detected")
            self.logger.info("COLMAP detection completed: version=%s", self._detection.version)
        else:
            self.colmap_version_label.setText("Version: not detected")
            self.detection_status_label.setObjectName("statusError")
            self.detection_status_label.setText(f"Detection status: {self._detection.error}")
            self.logger.warning("COLMAP detection completed: %s", self._detection.error)
        self.detection_status_label.style().unpolish(self.detection_status_label)
        self.detection_status_label.style().polish(self.detection_status_label)

    # -- refresh --------------------------------------------------------------------------

    def refresh(self) -> None:
        current = self.project_manager.current
        if current is None:
            self.active_project_label.setText("Active Project: (none open)")
            self.active_version_label.setText("")
            self.image_folder_label.setText("")
            self.image_count_label.setText("")
            self.validation_status_label.setText("")
            self.pipeline_widget.set_all("Not Started")
            return

        self.active_project_label.setText(f"Active Project: {current.data.name}")
        self.active_version_label.setText(f"Active Version: {current.data.version}")

        image_dir = current.resolver.images
        self.image_folder_label.setText(f"Image Folder: {current.data.relative_paths.images}")
        image_count = sum(1 for p in image_dir.iterdir() if p.is_file()) if image_dir.is_dir() else 0
        self.image_count_label.setText(f"Image Count: {image_count}")

        validation_status = current.data.validation_info.get("validationStatus", "notValidated")
        self.validation_status_label.setText(f"Input Validation Status: {validation_status}")

        state = self.manager.get_reconstruction_state()
        self.pipeline_widget.apply_reconstruction_state(state)

        analysis = current.data.colmap_info.get("analysis", {}) or {}
        if analysis.get("completed"):
            self._display_metrics(analysis)

    def _open_image_folder(self) -> None:
        if self.project_manager.current is None:
            return
        path = self.manager.active_image_source_path()
        if not path.is_dir():
            QMessageBox.warning(self, "Folder Not Found", f"This folder does not exist yet:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # -- pipeline entry points --------------------------------------------------------------

    def _on_run_full_pipeline(self) -> None:
        if not self._begin_run():
            return
        self._pending_steps = list(_STEP_ORDER)
        self._running_full_pipeline = True
        self._advance_pipeline()

    def _on_run_selected_step(self) -> None:
        if not self._begin_run():
            return
        self._pending_steps = [self.step_selector.currentText()]
        self._running_full_pipeline = False
        self._advance_pipeline()

    def _begin_run(self) -> bool:
        """Shared preconditions for both 'Run Full Pipeline' and 'Run
        Selected Step': project open, validation gate, COLMAP detected,
        preflight. Returns True if it is safe to proceed."""
        if self.project_manager.current is None:
            QMessageBox.warning(self, "No Project Open", "Open or create a project first.")
            return False

        try:
            allowed, requires_confirmation, message = self.manager.check_input_validation_gate()
        except ProjectLoadError as exc:
            QMessageBox.warning(self, "No Project Open", str(exc))
            return False

        if not allowed:
            QMessageBox.critical(self, "Cannot Run COLMAP", message)
            return False
        if requires_confirmation:
            reply = QMessageBox.question(self, "Continue?", message)
            if reply != QMessageBox.StandardButton.Yes:
                return False

        if self._detection is None or not self._detection.detected:
            self._detect_colmap()
        if self._detection is None or not self._detection.detected:
            QMessageBox.critical(
                self, "COLMAP Not Found", "COLMAP could not be detected. Configure its path first."
            )
            return False

        self.manager.config = self.settings_widget.apply_to_config(self.manager.config)

        preflight = self.manager.run_preflight(self._detection)
        if not preflight.all_passed:
            failed = "\n".join(f"- {c.name}: {c.message}" for c in preflight.failed_checks)
            QMessageBox.critical(self, "Preflight Failed", f"Cannot proceed:\n\n{failed}")
            self.logger.warning("COLMAP preflight failed:\n%s", failed)
            return False

        # Per the current architecture, COLMAP reads rawData/images/vNN
        # directly -- no persistent colmap/vNN/images junction is
        # created or required (removed to decouple COLMAP workspace
        # validation from a Windows junction).
        self._cancel_requested = False
        return True

    # -- sequential step execution -----------------------------------------------------------

    def _advance_pipeline(self) -> None:
        if not self._pending_steps:
            self._running_full_pipeline = False
            self._append_log("Pipeline finished.")
            self.refresh()
            self.pipeline_finished.emit()
            return
        step = self._pending_steps.pop(0)
        self._run_step(step)

    def _run_step(self, step: str) -> None:
        current = self.project_manager.current
        try:
            command = self._build_step_command(step)
        except (DatabaseExistsError, SparseModelExistsError) as exc:
            if not self._confirm_replace(step, str(exc)):
                self._abort_pipeline(f"{step} skipped by user.")
                return
            command = self._build_step_command(step, force=True)
        except ProjectLoadError as exc:
            QMessageBox.warning(self, "No Project Open", str(exc))
            self._abort_pipeline(str(exc))
            return

        self._current_step = step
        self.pipeline_widget.set_status(step, STATUS_RUNNING)
        self.command_preview_label.setText(command.display_command)
        self._append_log(f"$ {command.display_command}")
        self.logger.info("%s started: %s", step, command.display_command)

        self._process = ManagedProcess(self)
        self._process.output_line.connect(self._append_log)
        self._process.error_line.connect(self._append_log)
        self._process.finished_result.connect(
            lambda result: self._on_step_finished(step, command, result)
        )
        self.stop_button.setEnabled(True)
        start_colmap_command(self._process, command, cwd=current.project_root if current else None)

    def _build_step_command(self, step: str, force: bool = False) -> ColmapCommand:
        if step == "Database":
            return self.manager.create_database(force=force)
        if step == "Features":
            return self.manager.build_feature_extraction_command()
        if step == "Matching":
            return self.manager.build_feature_matching_command()
        if step == "Mapper":
            return self.manager.run_mapper(force=force)
        if step == "Analysis":
            return self.manager.build_model_analyzer_command()
        raise ValueError(f"Unknown pipeline step: {step}")

    def _confirm_replace(self, step: str, message: str) -> bool:
        reply = QMessageBox.question(
            self,
            f"{step} Already Exists",
            f"{message}\n\nReplace it? This will not touch other reconstruction data.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _on_step_finished(self, step: str, command: ColmapCommand, result: ProcessResult) -> None:
        self.stop_button.setEnabled(False)
        self.logger.info("%s finished: exit_code=%s", step, result.exit_code)

        if self._cancel_requested:
            self.pipeline_widget.set_status(step, STATUS_FAILED)
            self._append_log(f"{step} cancelled by user.")
            self.logger.warning("COLMAP process cancelled: %s", step)
            self._abort_pipeline(f"{step} cancelled.")
            self.refresh()
            return

        if result.exit_code != 0:
            self.pipeline_widget.set_status(step, STATUS_FAILED)
            self._append_log(f"{step} FAILED (exit code {result.exit_code}).")
            if result.stderr:
                self._append_log(result.stderr)
            self.logger.error("COLMAP process failed: %s (exit code %s)", step, result.exit_code)
            QMessageBox.critical(
                self, f"{step} Failed",
                f"COLMAP {step} failed with exit code {result.exit_code}.\n\nSee the log below for details.",
            )
            self._abort_pipeline(f"{step} failed.")
            return

        ok, message = self._verify_step_output(step)
        if not ok:
            self.pipeline_widget.set_status(step, STATUS_FAILED)
            self._append_log(f"{step} completed but expected output is missing: {message}")
            self.logger.error("COLMAP step output missing: %s (%s)", step, message)
            QMessageBox.critical(self, f"{step} Failed", message)
            self._abort_pipeline(message)
            return

        self._record_step_completion(step, result)
        self.pipeline_widget.set_status(step, STATUS_COMPLETED)
        self._append_log(f"{step} completed successfully.")
        self.logger.info("%s completed", step)
        self.refresh()

        if self._running_full_pipeline:
            self._advance_pipeline()

    def _verify_step_output(self, step: str) -> tuple[bool, str]:
        if step == "Database":
            ok = self.manager.database_exists()
            return ok, f"Expected database file not found at {self.manager.database_path()}"
        if step in ("Features", "Matching"):
            ok = self.manager.database_exists()
            return ok, "database.db is missing after this step."
        if step == "Mapper":
            ok = self.manager.sparse_model_exists()
            return ok, f"Expected sparse model files not found at {self.manager.sparse_model_path()}"
        return True, ""

    def _record_step_completion(self, step: str, result: ProcessResult) -> None:
        if step == "Database":
            self.manager.record_database_created()
        elif step == "Features":
            self.manager.record_feature_extraction_completed(
                self.manager.config.feature_extraction_use_gpu,
                self.manager.config.feature_extraction_threads,
            )
        elif step == "Matching":
            self.manager.record_feature_matching_completed(
                self.manager.config.feature_matching_use_gpu, self.manager.config.matcher_type
            )
        elif step == "Mapper":
            self.manager.record_mapper_completed()
        elif step == "Analysis":
            metrics = parse_model_analyzer_output(result.stdout + "\n" + result.stderr)
            self.manager.record_analysis_completed(metrics)
            self._display_metrics(metrics)

    def _display_metrics(self, metrics: dict) -> None:
        total = metrics.get("totalImages", 0)
        registered = metrics.get("registeredImages", 0)
        percentage = calculate_registration_percentage(registered, total)
        self.metrics_label.setText(
            f"Total Images: {total}   Registered: {registered} ({percentage:.1f}%)   "
            f"Points: {metrics.get('points', 0):,}   Observations: {metrics.get('observations', 0):,}   "
            f"Mean Track Length: {metrics.get('meanTrackLength', 0):.3f}   "
            f"Mean Reprojection Error: {metrics.get('meanReprojectionError', 0):.3f} px"
        )

    def _abort_pipeline(self, message: str) -> None:
        self._pending_steps = []
        self._running_full_pipeline = False
        self._current_step = None
        self.pipeline_finished.emit()

    def _on_stop_clicked(self) -> None:
        if self._process is not None and self._process.is_running():
            self._cancel_requested = True
            self._process.cancel()
            self._append_log("Cancellation requested...")

    def _copy_command_to_clipboard(self) -> None:
        text = self.command_preview_label.text()
        if text and text != "(no command run yet)":
            QApplication.clipboard().setText(text, QClipboard.Mode.Clipboard)

    def _append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
