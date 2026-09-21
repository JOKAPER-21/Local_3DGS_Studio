"""Dashboard page: read-only overview of the open project and hardware,
plus the project-level actions (New Project / Open Project) that used to
live as persistent sidebar chrome. Per the redesign, these are
contextual to Dashboard rather than always-visible controls -- emitted
as signals so this page never has to know about ``MainWindow``, the
same pattern already used by ``ProjectsSetupPage.project_created``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.core.hardware_monitor import read_system_info
from src.core.project_manager import ProjectManager
from src.utils.filesystem import human_readable_size


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    heading = QLabel(title)
    heading.setObjectName("sectionLabel")
    layout.addWidget(heading)
    return frame, layout


class DashboardPage(QWidget):
    new_project_requested = Signal()
    open_project_requested = Signal()

    def __init__(self, project_manager: ProjectManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_manager = project_manager

        outer = QVBoxLayout(self)
        header_row = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("pageTitle")
        header_row.addWidget(title)
        header_row.addStretch(1)
        new_project_button = QPushButton("New Project")
        new_project_button.setObjectName("secondaryButton")
        new_project_button.clicked.connect(self.new_project_requested.emit)
        open_project_button = QPushButton("Open Project")
        open_project_button.setObjectName("secondaryButton")
        open_project_button.clicked.connect(self.open_project_requested.emit)
        header_row.addWidget(new_project_button)
        header_row.addWidget(open_project_button)
        outer.addLayout(header_row)

        grid = QGridLayout()
        grid.setSpacing(12)
        outer.addLayout(grid)

        # -- project card ---------------------------------------------------
        project_card, project_layout = _card("Project")
        self.project_name_label = QLabel("No project open")
        self.project_path_label = QLabel("")
        self.project_version_label = QLabel("")
        self.image_count_label = QLabel("")
        for label in (
            self.project_name_label,
            self.project_path_label,
            self.project_version_label,
            self.image_count_label,
        ):
            label.setWordWrap(True)
            project_layout.addWidget(label)
        grid.addWidget(project_card, 0, 0)

        # -- pipeline status card ---------------------------------------------
        status_card, status_layout = _card("Pipeline Status")
        self.colmap_status_label = QLabel("COLMAP: not started")
        self.lichtfeld_status_label = QLabel("LichtFeld: not started")
        self.training_status_label = QLabel("Training: not started")
        self.export_status_label = QLabel("Export: not started")
        self.render_status_label = QLabel("Render: not started")
        for label in (
            self.colmap_status_label,
            self.lichtfeld_status_label,
            self.training_status_label,
            self.export_status_label,
            self.render_status_label,
        ):
            status_layout.addWidget(label)
        grid.addWidget(status_card, 0, 1)

        # -- hardware card ----------------------------------------------------
        hw_card, hw_layout = _card("Hardware")
        self.gpu_label = QLabel("GPU: detecting...")
        self.vram_label = QLabel("")
        self.ram_label = QLabel("")
        self.disk_label = QLabel("")
        for label in (self.gpu_label, self.vram_label, self.ram_label, self.disk_label):
            hw_layout.addWidget(label)
        grid.addWidget(hw_card, 1, 0, 1, 2)

        outer.addStretch(1)

        self._hw_timer = QTimer(self)
        self._hw_timer.setInterval(3000)
        self._hw_timer.timeout.connect(self.refresh_hardware)
        self._hw_timer.start()

        self.refresh()

    def refresh(self) -> None:
        self.refresh_project_info()
        self.refresh_hardware()

    def refresh_project_info(self) -> None:
        current = self.project_manager.current
        if current is None:
            self.project_name_label.setText("No project open")
            self.project_path_label.setText("")
            self.project_version_label.setText("")
            self.image_count_label.setText("")
            return

        self.project_name_label.setText(f"<b>{current.data.name}</b>")
        self.project_path_label.setText(f"Path: {current.project_root}")
        self.project_version_label.setText(f"Active version: {current.data.version}")
        image_count = current.data.input_info.get("imageCount", 0)
        self.image_count_label.setText(f"Images: {image_count}")

        training_status = current.data.lichtfeld_info.get("trainingStatus", "notStarted")
        self.lichtfeld_status_label.setText(f"LichtFeld: {training_status}")
        self.training_status_label.setText(f"Training: {training_status}")

        registered = current.data.colmap_info.get("registeredImages", 0)
        colmap_state = "not started" if registered == 0 else f"{registered} images registered"
        self.colmap_status_label.setText(f"COLMAP: {colmap_state}")

    def refresh_hardware(self) -> None:
        project_disk = (
            self.project_manager.current.project_root
            if self.project_manager.current is not None
            else None
        )
        info = read_system_info(project_disk)

        if info.gpu and info.gpu.available:
            self.gpu_label.setText(f"GPU: {info.gpu.name}")
            self.vram_label.setText(
                f"VRAM: {info.gpu.vram_used_mb} / {info.gpu.vram_total_mb} MB   "
                f"Util: {info.gpu.utilization_percent}%   Temp: {info.gpu.temperature_c}°C"
            )
        else:
            self.gpu_label.setText("GPU: not detected")
            self.vram_label.setText("")

        self.ram_label.setText(
            f"RAM: {info.ram_used_gb:.1f} / {info.ram_total_gb:.1f} GB"
        )
        self.disk_label.setText(
            f"Disk free: {human_readable_size(int(info.disk_free_gb * 1024 ** 3))} "
            f"of {human_readable_size(int(info.disk_total_gb * 1024 ** 3))}"
        )
