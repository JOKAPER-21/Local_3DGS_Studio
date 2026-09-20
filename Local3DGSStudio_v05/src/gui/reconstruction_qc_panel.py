"""Reconstruction QC page: displays the verdict from ``ReconstructionQC``
(READY / WARNING / FAILED / NOT_READY) with every metric the
specification calls for, plus Refresh QC and Open Reconstruction Folder.

All QC arithmetic lives in ``src/core/reconstruction_qc.py`` -- this page
only asks ``ReconstructionQC.run()`` for a ``QCResult`` and renders it.
No blocking ``QMessageBox`` calls are used so this page is safe inside
headless/automated tests as well as the normal GUI.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.project_manager import ProjectLoadError, ProjectManager
from src.core.reconstruction_qc import (
    QC_STATE_FAILED,
    QC_STATE_NOT_READY,
    QC_STATE_READY,
    QC_STATE_WARNING,
    QCResult,
    ReconstructionQC,
)

_STATE_LABEL_OBJECT_NAMES = {
    QC_STATE_READY: "statusOk",
    QC_STATE_WARNING: "statusWarning",
    QC_STATE_FAILED: "statusError",
    QC_STATE_NOT_READY: "statusMuted",
}

# Text markers so status is never conveyed by color alone (per the
# specification's display rule).
_STATE_MARKERS = {
    QC_STATE_READY: "\u25cf READY",
    QC_STATE_WARNING: "\u25cf WARNING",
    QC_STATE_FAILED: "\u25cf FAILED",
    QC_STATE_NOT_READY: "\u25cb NOT READY",
}


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


class ReconstructionQCPage(QWidget):
    def __init__(self, project_manager: ProjectManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_manager = project_manager
        self.qc = ReconstructionQC(project_manager)
        self._last_result: QCResult | None = None

        outer = QVBoxLayout(self)
        title = QLabel("Reconstruction QC")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        # -- status banner -----------------------------------------------------
        self.status_label = QLabel(_STATE_MARKERS[QC_STATE_NOT_READY])
        self.status_label.setObjectName(_STATE_LABEL_OBJECT_NAMES[QC_STATE_NOT_READY])
        self.status_label.setStyleSheet("font-size: 14pt; font-weight: 700;")
        outer.addWidget(self.status_label)

        self.checked_at_label = QLabel("Last checked: never")
        self.checked_at_label.setObjectName("statusMuted")
        outer.addWidget(self.checked_at_label)

        grid = QGridLayout()
        grid.setSpacing(12)
        outer.addLayout(grid)

        # -- images card -------------------------------------------------------
        images_card, images_layout = _card("Images")
        row, self.total_images_value = _stat_row("Total")
        images_layout.addWidget(row)
        row, self.registered_images_value = _stat_row("Registered")
        images_layout.addWidget(row)
        row, self.registration_pct_value = _stat_row("Registration")
        images_layout.addWidget(row)
        grid.addWidget(images_card, 0, 0)

        # -- sparse reconstruction card -----------------------------------------
        sparse_card, sparse_layout = _card("Sparse Reconstruction")
        row, self.points_value = _stat_row("Points")
        sparse_layout.addWidget(row)
        row, self.observations_value = _stat_row("Observations")
        sparse_layout.addWidget(row)
        row, self.track_length_value = _stat_row("Track Length")
        sparse_layout.addWidget(row)
        grid.addWidget(sparse_card, 0, 1)

        # -- camera card -------------------------------------------------------------
        camera_card, camera_layout = _card("Camera")
        row, self.cameras_value = _stat_row("Cameras")
        camera_layout.addWidget(row)
        row, self.registered_cameras_value = _stat_row("Registered")
        camera_layout.addWidget(row)
        row, self.camera_models_value = _stat_row("Model(s)")
        camera_layout.addWidget(row)
        row, self.distortion_value = _stat_row("Distortion")
        camera_layout.addWidget(row)
        grid.addWidget(camera_card, 1, 0)

        # -- quality card -------------------------------------------------------------
        quality_card, quality_layout = _card("Quality")
        row, self.reprojection_value = _stat_row("Reprojection")
        quality_layout.addWidget(row)
        row, self.required_files_value = _stat_row("Required Files")
        quality_layout.addWidget(row)
        row, self.database_value = _stat_row("Database")
        quality_layout.addWidget(row)
        row, self.image_source_value = _stat_row("Image Source")
        quality_layout.addWidget(row)
        grid.addWidget(quality_card, 1, 1)

        # -- warnings / errors -----------------------------------------------------
        outer.addWidget(self._label("Warnings"))
        self.warnings_view = QPlainTextEdit()
        self.warnings_view.setReadOnly(True)
        self.warnings_view.setMaximumHeight(90)
        outer.addWidget(self.warnings_view)

        outer.addWidget(self._label("Errors"))
        self.errors_view = QPlainTextEdit()
        self.errors_view.setReadOnly(True)
        self.errors_view.setMaximumHeight(90)
        outer.addWidget(self.errors_view)

        # -- actions -------------------------------------------------------------------
        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh QC")
        self.refresh_button.clicked.connect(self.run_qc)
        self.open_folder_button = QPushButton("Open Reconstruction Folder")
        self.open_folder_button.setObjectName("secondaryButton")
        self.open_folder_button.clicked.connect(self._open_reconstruction_folder)
        # Phase 06 will enable this once the reconstruction is
        # send-to-LichtFeld eligible; kept visible but disabled here so
        # the future gate is legible without implementing training yet.
        self.send_to_lichtfeld_button = QPushButton("Send to LichtFeld")
        self.send_to_lichtfeld_button.setObjectName("secondaryButton")
        self.send_to_lichtfeld_button.setEnabled(False)
        self.send_to_lichtfeld_button.setToolTip("Available starting in Phase 06.")
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.open_folder_button)
        actions.addWidget(self.send_to_lichtfeld_button)
        actions.addStretch(1)
        outer.addLayout(actions)

        outer.addStretch(1)

        self.refresh()

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    # -- refresh / run --------------------------------------------------------------

    def refresh(self) -> None:
        """Re-display the persisted QC result without re-running QC.
        Used on plain page navigation / project switches; ``run_qc``
        (below) is the one that actually re-evaluates evidence."""
        if self.project_manager.current is None:
            self._display_empty("No project open.")
            return

        stored = self.project_manager.current.data.reconstruction_qc_info
        if not stored:
            self._display_empty("Not checked yet. Click Refresh QC.")
            return

        result = self._result_from_stored(stored)
        self._display(result)

    def run_qc(self) -> None:
        """Actually re-run QC against current disk evidence and persist
        the result (via ``ReconstructionQC.run``), then display it."""
        try:
            result = self.qc.run()
        except ProjectLoadError:
            self._display_empty("No project open.")
            return
        self._display(result)

    def _result_from_stored(self, stored: dict) -> QCResult:
        return QCResult(
            total_images=stored.get("totalImages", 0),
            registered_images=stored.get("registeredImages", 0),
            registration_percentage=stored.get("registrationPercentage", 0.0),
            cameras=stored.get("cameras", 0),
            registered_cameras=stored.get("registeredCameras", 0),
            frames=stored.get("frames", 0),
            registered_frames=stored.get("registeredFrames", 0),
            points=stored.get("points", 0),
            observations=stored.get("observations", 0),
            mean_track_length=stored.get("meanTrackLength"),
            mean_observations_per_image=stored.get("meanObservationsPerImage"),
            mean_reprojection_error_px=stored.get("meanReprojectionErrorPx"),
            camera_models=stored.get("cameraModels", []) or [],
            distorted_camera_models=stored.get("distortedCameraModels", []) or [],
            required_files_present=stored.get("requiredFilesPresent", False),
            database_valid=stored.get("databaseValid", False),
            image_source_valid=stored.get("imageSourceValid", False),
            state=stored.get("state", QC_STATE_NOT_READY),
            warnings=stored.get("warnings", []) or [],
            errors=stored.get("errors", []) or [],
            checked_at=stored.get("lastCheckedAt", ""),
        )

    # -- rendering -------------------------------------------------------------------

    def _display_empty(self, message: str) -> None:
        self._last_result = None
        self.status_label.setText(_STATE_MARKERS[QC_STATE_NOT_READY])
        self._set_status_object_name(QC_STATE_NOT_READY)
        self.checked_at_label.setText(message)
        for value_label in (
            self.total_images_value, self.registered_images_value, self.registration_pct_value,
            self.points_value, self.observations_value, self.track_length_value,
            self.cameras_value, self.registered_cameras_value, self.camera_models_value,
            self.distortion_value, self.reprojection_value, self.required_files_value,
            self.database_value, self.image_source_value,
        ):
            value_label.setText("--")
        self.warnings_view.setPlainText("")
        self.errors_view.setPlainText("")
        self.send_to_lichtfeld_button.setEnabled(False)

    def _display(self, result: QCResult) -> None:
        self._last_result = result

        self.status_label.setText(_STATE_MARKERS.get(result.state, result.state))
        self._set_status_object_name(result.state)
        self.checked_at_label.setText(
            f"Last checked: {result.checked_at}" if result.checked_at else "Last checked: never"
        )

        self.total_images_value.setText(str(result.total_images))
        self.registered_images_value.setText(str(result.registered_images))
        self.registration_pct_value.setText(f"{result.registration_percentage:.1f}%")

        self.points_value.setText(f"{result.points:,}")
        self.observations_value.setText(f"{result.observations:,}")
        self.track_length_value.setText(
            f"{result.mean_track_length:.3f}" if result.mean_track_length is not None else "n/a"
        )

        self.cameras_value.setText(str(result.cameras))
        self.registered_cameras_value.setText(str(result.registered_cameras))
        self.camera_models_value.setText(", ".join(result.camera_models) or "n/a")
        self.distortion_value.setText(
            ", ".join(result.distorted_camera_models) if result.distorted_camera_models else "None detected"
        )

        self.reprojection_value.setText(
            f"{result.mean_reprojection_error_px:.3f} px"
            if result.mean_reprojection_error_px is not None
            else "n/a"
        )
        self.required_files_value.setText("Present" if result.required_files_present else "Missing")
        self.database_value.setText("Valid" if result.database_valid else "Invalid")
        self.image_source_value.setText("Valid" if result.image_source_valid else "Invalid")

        self.warnings_view.setPlainText(
            "\n".join(f"- {w}" for w in result.warnings) if result.warnings else "(none)"
        )
        self.errors_view.setPlainText(
            "\n".join(f"- {e}" for e in result.errors) if result.errors else "(none)"
        )

        # Phase 06 will wire this to the actual LichtFeld hand-off; for
        # now it simply reflects whether QC considers the reconstruction
        # usable, per QCResult.is_ready_for_lichtfeld.
        self.send_to_lichtfeld_button.setEnabled(result.is_ready_for_lichtfeld)

    def _set_status_object_name(self, state: str) -> None:
        object_name = _STATE_LABEL_OBJECT_NAMES.get(state, "statusMuted")
        self.status_label.setObjectName(object_name)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _open_reconstruction_folder(self) -> None:
        if self.project_manager.current is None:
            return
        path = self.project_manager.current.resolver.colmap
        if not path.is_dir():
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
