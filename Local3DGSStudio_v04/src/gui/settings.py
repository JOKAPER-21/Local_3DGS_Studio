"""Settings page: external software paths (with auto-detect + manual
override) and the default project root."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.config_manager import AppSettings, ConfigManager
from src.core.software_detector import detect_all


class SettingsPage(QWidget):
    def __init__(self, config_manager: ConfigManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.settings: AppSettings = self.config_manager.load_settings()

        outer = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)

        card_layout.addWidget(self._label("Default Project Root"))
        self.default_root_edit = QLineEdit(self.settings.default_project_root)
        card_layout.addWidget(self._path_row(self.default_root_edit, is_folder=True))

        card_layout.addWidget(self._label("COLMAP Path"))
        self.colmap_edit = QLineEdit(self.settings.external_software.colmap)
        self.colmap_status = QLabel("")
        card_layout.addWidget(self._path_row(self.colmap_edit, is_folder=False))
        card_layout.addWidget(self.colmap_status)

        card_layout.addWidget(self._label("LichtFeld Studio Path"))
        self.lichtfeld_edit = QLineEdit(self.settings.external_software.lichtfeld)
        self.lichtfeld_status = QLabel("")
        card_layout.addWidget(self._path_row(self.lichtfeld_edit, is_folder=False))
        card_layout.addWidget(self.lichtfeld_status)

        card_layout.addWidget(self._label("FFmpeg Path (optional)"))
        self.ffmpeg_edit = QLineEdit(self.settings.external_software.ffmpeg)
        self.ffmpeg_status = QLabel("")
        card_layout.addWidget(self._path_row(self.ffmpeg_edit, is_folder=False))
        card_layout.addWidget(self.ffmpeg_status)

        outer.addWidget(card)

        button_row = QHBoxLayout()
        detect_button = QPushButton("Auto-Detect")
        detect_button.setObjectName("secondaryButton")
        detect_button.clicked.connect(self.auto_detect)
        save_button = QPushButton("Save Settings")
        save_button.clicked.connect(self.save)
        button_row.addWidget(detect_button)
        button_row.addWidget(save_button)
        outer.addLayout(button_row)

        self.save_result_label = QLabel("")
        outer.addWidget(self.save_result_label)

        outer.addStretch(1)
        self.auto_detect()

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _path_row(self, edit: QLineEdit, is_folder: bool) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit)
        browse_button = QPushButton("Browse...")
        browse_button.setObjectName("secondaryButton")

        def browse() -> None:
            if is_folder:
                path = QFileDialog.getExistingDirectory(self, "Select Folder")
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Select Executable")
            if path:
                edit.setText(path)

        browse_button.clicked.connect(browse)
        layout.addWidget(browse_button)
        return row

    def auto_detect(self) -> None:
        overrides = {
            "colmap": self.colmap_edit.text().strip(),
            "lichtfeld": self.lichtfeld_edit.text().strip(),
            "ffmpeg": self.ffmpeg_edit.text().strip(),
        }
        results = detect_all(overrides)

        for key, edit, status_label in (
            ("colmap", self.colmap_edit, self.colmap_status),
            ("lichtfeld", self.lichtfeld_edit, self.lichtfeld_status),
            ("ffmpeg", self.ffmpeg_edit, self.ffmpeg_status),
        ):
            result = results[key]
            if result.found:
                if not edit.text().strip():
                    edit.setText(result.path)
                status_label.setObjectName("statusOk")
                status_label.setText(f"Detected via {result.source}: {result.path}")
            else:
                status_label.setObjectName("statusWarning")
                status_label.setText("Not detected -- select the path manually.")
            status_label.style().unpolish(status_label)
            status_label.style().polish(status_label)

    def save(self) -> None:
        self.settings.default_project_root = self.default_root_edit.text().strip()
        self.settings.external_software.colmap = self.colmap_edit.text().strip()
        self.settings.external_software.lichtfeld = self.lichtfeld_edit.text().strip()
        self.settings.external_software.ffmpeg = self.ffmpeg_edit.text().strip()
        self.config_manager.save_settings(self.settings)
        self.save_result_label.setObjectName("statusOk")
        self.save_result_label.setText("Settings saved.")
