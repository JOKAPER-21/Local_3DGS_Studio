"""Reconstruction workspace: wraps the existing ``ReconstructionQCPage``
as an "Overview / Quality Control" tab, alongside two new tabs -- Sparse
Point Cloud and Camera Poses.

Per the "Gaussian preview architecture" requirement, phase 1 is a COLMAP
sparse point cloud preview; a full 3D viewport is not implemented yet.
These two tabs show real numbers read from the already-persisted
``reconstructionQC`` section (never recomputed here, never a fake
render) and say plainly that the 3D view itself is future work -- they
exist so the workspace layout is extensible without pretending
something is rendered when it isn't.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from src.core.project_manager import ProjectManager
from src.core.reconstruction_qc import QCResult


class SparsePointCloudTab(QWidget):
    def __init__(self, project_manager: ProjectManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_manager = project_manager

        layout = QVBoxLayout(self)
        title = QLabel("Sparse Point Cloud")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        note = QLabel(
            "This is the COLMAP sparse reconstruction (matched feature points), "
            "not a trained Gaussian Splat. A 3D viewport is not implemented yet "
            "-- the numbers below come directly from the last Reconstruction QC "
            "run."
        )
        note.setWordWrap(True)
        note.setObjectName("statusMuted")
        layout.addWidget(note)

        self.numbers_label = QLabel("--")
        layout.addWidget(self.numbers_label)
        layout.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        current = self.project_manager.current
        if current is None:
            self.numbers_label.setText("--")
            return
        result = QCResult.from_project_json_dict(current.data.reconstruction_qc_info)
        self.numbers_label.setText(
            f"{result.points:,} points    {result.observations:,} observations"
        )


class CameraPosesTab(QWidget):
    def __init__(self, project_manager: ProjectManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_manager = project_manager

        layout = QVBoxLayout(self)
        title = QLabel("Camera Poses")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        note = QLabel(
            "Registered camera positions and orientations from the COLMAP "
            "reconstruction. A 3D camera-frustum preview is not implemented "
            "yet -- the counts below come directly from the last Reconstruction "
            "QC run."
        )
        note.setWordWrap(True)
        note.setObjectName("statusMuted")
        layout.addWidget(note)

        self.numbers_label = QLabel("--")
        layout.addWidget(self.numbers_label)
        layout.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        current = self.project_manager.current
        if current is None:
            self.numbers_label.setText("--")
            return
        result = QCResult.from_project_json_dict(current.data.reconstruction_qc_info)
        self.numbers_label.setText(
            f"{result.registered_cameras:,} registered of {result.cameras:,} cameras "
            f"({', '.join(result.camera_models) or 'unknown model'})"
        )


class ReconstructionWorkspace(QWidget):
    """The "Reconstruction" workflow page: a tab strip over the existing
    ``ReconstructionQCPage`` (unchanged) plus the two informational tabs
    above. ``refresh()`` delegates to all three -- no QC math lives
    here."""

    def __init__(self, qc_page: QWidget, project_manager: ProjectManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.qc_page = qc_page

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.addTab(qc_page, "Overview / Quality Control")
        self.point_cloud_tab = SparsePointCloudTab(project_manager)
        self.tabs.addTab(self.point_cloud_tab, "Sparse Point Cloud")
        self.camera_poses_tab = CameraPosesTab(project_manager)
        self.tabs.addTab(self.camera_poses_tab, "Camera Poses")
        layout.addWidget(self.tabs)

    def refresh(self) -> None:
        self.qc_page.refresh()
        self.point_cloud_tab.refresh()
        self.camera_poses_tab.refresh()
