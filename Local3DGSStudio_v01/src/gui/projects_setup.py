"""Projects Setup page: one-click project creation.

Layout follows the specification exactly: Project Root selector, Project
Name input, Version input, a live path/folder-tree preview, and a single
"Projects Setup" button. All path construction and validation happens in
core (ProjectManager / ProjectStructureManager / validators) -- this page
only collects input and displays results.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.project_manager import ProjectManager
from src.core.project_structure import ProjectAlreadyExistsError
from src.utils.validators import ValidationError


def _preview_tree(project_path: Path, project_name: str, version: str) -> str:
    lines = [
        project_name,
        "├── project.json",
        "├── rawData",
        "│   ├── images",
        f"│   │   └── {version}",
        "│   └── videos",
        "├── colmap",
        f"│   └── {version}",
        "├── export",
        "│   ├── pointCloud",
        "│   └── splats",
        "├── renders",
        "└── logs",
    ]
    return "\n".join(lines)


class ProjectsSetupPage(QWidget):
    project_created = Signal()

    def __init__(self, project_manager: ProjectManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_manager = project_manager

        outer = QVBoxLayout(self)
        title = QLabel("Projects Setup")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        form_card = QFrame()
        form_card.setObjectName("card")
        form_layout = QVBoxLayout(form_card)

        # Project root
        form_layout.addWidget(self._label("Project Root"))
        root_row = QHBoxLayout()
        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText(r"J:\Projects_3DGS")
        browse_button = QPushButton("Browse...")
        browse_button.setObjectName("secondaryButton")
        browse_button.clicked.connect(self._browse_root)
        root_row.addWidget(self.root_edit)
        root_row.addWidget(browse_button)
        form_layout.addLayout(root_row)

        # Project name
        form_layout.addWidget(self._label("Project Name"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("gsOfficeBuildingPillar")
        form_layout.addWidget(self.name_edit)

        # Version
        form_layout.addWidget(self._label("Version"))
        self.version_edit = QLineEdit("v01")
        form_layout.addWidget(self.version_edit)

        for edit in (self.root_edit, self.name_edit, self.version_edit):
            edit.textChanged.connect(self._update_preview)

        outer.addWidget(form_card)

        # Preview card
        preview_card = QFrame()
        preview_card.setObjectName("card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.addWidget(self._label("Project Path Preview"))
        self.path_preview_label = QLabel("")
        self.path_preview_label.setWordWrap(True)
        preview_layout.addWidget(self.path_preview_label)

        preview_layout.addWidget(self._label("Folder Structure Preview"))
        self.tree_preview = QPlainTextEdit()
        self.tree_preview.setReadOnly(True)
        self.tree_preview.setMaximumHeight(220)
        preview_layout.addWidget(self.tree_preview)

        outer.addWidget(preview_card)

        # Primary action
        self.setup_button = QPushButton("Projects Setup")
        self.setup_button.clicked.connect(self._on_setup_clicked)
        outer.addWidget(self.setup_button)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        outer.addWidget(self.result_label)

        outer.addStretch(1)

        self._update_preview()

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _browse_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Project Root")
        if folder:
            self.root_edit.setText(folder)

    def _update_preview(self) -> None:
        root = self.root_edit.text().strip()
        name = self.name_edit.text().strip()
        version = self.version_edit.text().strip() or "v01"

        if root and name:
            full_path = Path(root) / name
            self.path_preview_label.setText(str(full_path))
            self.tree_preview.setPlainText(_preview_tree(full_path, name, version))
        else:
            self.path_preview_label.setText("(enter a project root and name)")
            self.tree_preview.setPlainText("")

    def _on_setup_clicked(self) -> None:
        root = self.root_edit.text().strip()
        name = self.name_edit.text().strip()
        version = self.version_edit.text().strip()

        try:
            opened = self.project_manager.create_project(root, name, version)
        except ValidationError as exc:
            QMessageBox.warning(self, "Invalid Input", str(exc))
            return
        except ProjectAlreadyExistsError as exc:
            reply = QMessageBox.question(
                self,
                "Project Already Exists",
                f"{exc}\n\nWould you like to open the existing project instead?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                existing_path = str(Path(root) / name)
                try:
                    self.project_manager.open_project(existing_path)
                    self.result_label.setObjectName("statusOk")
                    self.result_label.setText(f"Opened existing project at: {existing_path}")
                    self.project_created.emit()
                except Exception as open_exc:  # noqa: BLE001 - surface any load error
                    QMessageBox.critical(self, "Could Not Open Project", str(open_exc))
            return
        except OSError as exc:
            QMessageBox.critical(self, "Filesystem Error", str(exc))
            return

        self.result_label.setObjectName("statusOk")
        self.result_label.setText(
            f"Project created successfully at: {opened.project_root}"
        )
        self.project_created.emit()
