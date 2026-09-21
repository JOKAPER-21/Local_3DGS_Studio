"""Input page: displays the active project's resolved image/video
directories and lets the user open them in Explorer, refresh counts, or
create a new input version -- all without ever asking the user to browse
for the image directory of an existing project."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.input_manager import InputManager
from src.core.project_manager import ProjectLoadError, ProjectManager


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    heading = QLabel(title)
    heading.setObjectName("sectionLabel")
    layout.addWidget(heading)
    return frame, layout


class InputPage(QWidget):
    def __init__(self, project_manager: ProjectManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_manager = project_manager
        self.input_manager = InputManager(project_manager)

        outer = QVBoxLayout(self)
        title = QLabel("Input")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        # -- project info card --------------------------------------------------
        project_card, project_layout = _card("Project Information")
        self.project_label = QLabel("")
        self.version_label = QLabel("")
        self.root_label = QLabel("")
        for label in (self.project_label, self.version_label, self.root_label):
            label.setWordWrap(True)
            project_layout.addWidget(label)
        outer.addWidget(project_card)

        # -- images card --------------------------------------------------------
        images_card, images_layout = _card("Images")
        self.image_folder_label = QLabel("")
        self.image_resolved_label = QLabel("")
        self.image_count_label = QLabel("")
        for label in (self.image_folder_label, self.image_resolved_label, self.image_count_label):
            label.setWordWrap(True)
            images_layout.addWidget(label)

        image_buttons = QHBoxLayout()
        open_images_button = QPushButton("Open Image Folder")
        open_images_button.setObjectName("secondaryButton")
        open_images_button.clicked.connect(self._open_image_folder)
        refresh_images_button = QPushButton("Refresh")
        refresh_images_button.setObjectName("secondaryButton")
        refresh_images_button.clicked.connect(self.refresh)
        validate_button = QPushButton("Validate Images")
        validate_button.clicked.connect(self._go_to_validation)
        new_version_button = QPushButton("New Version")
        new_version_button.setObjectName("secondaryButton")
        new_version_button.clicked.connect(self._create_new_version)
        image_buttons.addWidget(open_images_button)
        image_buttons.addWidget(refresh_images_button)
        image_buttons.addWidget(validate_button)
        image_buttons.addWidget(new_version_button)
        images_layout.addLayout(image_buttons)
        outer.addWidget(images_card)

        # -- videos card --------------------------------------------------------
        videos_card, videos_layout = _card("Videos")
        self.video_folder_label = QLabel("")
        self.video_count_label = QLabel("")
        for label in (self.video_folder_label, self.video_count_label):
            label.setWordWrap(True)
            videos_layout.addWidget(label)

        video_buttons = QHBoxLayout()
        open_videos_button = QPushButton("Open Video Folder")
        open_videos_button.setObjectName("secondaryButton")
        open_videos_button.clicked.connect(self._open_video_folder)
        refresh_videos_button = QPushButton("Refresh")
        refresh_videos_button.setObjectName("secondaryButton")
        refresh_videos_button.clicked.connect(self.refresh)
        video_buttons.addWidget(open_videos_button)
        video_buttons.addWidget(refresh_videos_button)
        videos_layout.addLayout(video_buttons)
        outer.addWidget(videos_card)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

        outer.addStretch(1)
        self.refresh()

    # -- navigation hook, wired up by MainWindow -----------------------------
    on_navigate_to_validation = None  # type: ignore[assignment]

    def _go_to_validation(self) -> None:
        if callable(self.on_navigate_to_validation):
            self.on_navigate_to_validation()

    def refresh(self) -> None:
        current = self.project_manager.current
        if current is None:
            self.project_label.setText("No project open.")
            self.version_label.setText("")
            self.root_label.setText("")
            self.image_folder_label.setText("")
            self.image_resolved_label.setText("")
            self.image_count_label.setText("")
            self.video_folder_label.setText("")
            self.video_count_label.setText("")
            self.status_label.setObjectName("statusMuted")
            self.status_label.setText("Open or create a project to manage input data.")
            return

        self.project_label.setText(f"Project: <b>{current.data.name}</b>")
        self.version_label.setText(f"Project Version: {current.data.version}")
        self.root_label.setText(f"Project Root: {current.project_root}")

        images_relative = current.data.relative_paths.images
        images_absolute = self.input_manager.get_active_image_directory()
        self.image_folder_label.setText(f"Image Folder: {images_relative}")
        self.image_resolved_label.setText(f"Resolved Path: {images_absolute}")

        videos_absolute = self.input_manager.get_video_directory()
        self.video_folder_label.setText(
            f"Video Folder: {current.data.relative_paths.videos}"
        )

        try:
            self.input_manager.refresh_input_data()
            image_count = self.input_manager.count_images()
            video_count = self.input_manager.count_videos()
        except ProjectLoadError:
            image_count = 0
            video_count = 0

        self.image_count_label.setText(f"Image Count: {image_count}")
        self.video_count_label.setText(f"Video Count: {video_count}")

        if not images_absolute.is_dir():
            self.status_label.setObjectName("statusWarning")
            self.status_label.setText(
                "The active image directory is missing. Use Settings/repair, "
                "or create a new version."
            )
        elif image_count == 0:
            self.status_label.setObjectName("statusWarning")
            self.status_label.setText(
                "No images found yet. Copy your source images into the folder above."
            )
        else:
            self.status_label.setObjectName("statusOk")
            self.status_label.setText(f"{image_count} image(s) detected and ready to validate.")

        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _open_image_folder(self) -> None:
        self._open_in_explorer(self.input_manager.get_active_image_directory())

    def _open_video_folder(self) -> None:
        self._open_in_explorer(self.input_manager.get_video_directory())

    def _open_in_explorer(self, path) -> None:
        if not path.is_dir():
            QMessageBox.warning(
                self, "Folder Not Found", f"This folder does not exist yet:\n{path}"
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _create_new_version(self) -> None:
        if self.project_manager.current is None:
            return
        suggested = self.input_manager.next_version_string()
        version, ok = QInputDialog.getText(
            self, "New Version", "New version (format vNN):", text=suggested
        )
        if not ok or not version.strip():
            return
        try:
            new_version = self.input_manager.create_image_version(version.strip())
        except Exception as exc:  # noqa: BLE001 - surface any validation/IO error
            QMessageBox.critical(self, "Could Not Create Version", str(exc))
            return
        QMessageBox.information(
            self, "Version Created", f"Version {new_version} created and set active."
        )
        self.refresh()
