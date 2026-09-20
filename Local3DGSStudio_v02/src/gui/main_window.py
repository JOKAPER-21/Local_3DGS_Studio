"""Main application window: sidebar navigation + stacked pages.

Implements the startup sequence from the specification:
startApplication -> readLastProjectConfiguration -> checkProjectExists ->
validateProjectJson -> loadProject -> resolveProjectPaths -> refreshDashboard,
with graceful handling when the last project is missing or invalid.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.config_manager import ConfigManager
from src.core.logger import get_app_logger
from src.core.project_manager import ProjectLoadError, ProjectManager
from src.gui.dashboard import DashboardPage
from src.gui.image_validation import ImageValidationPage
from src.gui.input_panel import InputPage
from src.gui.logs import LogsPage
from src.gui.projects_setup import ProjectsSetupPage
from src.gui.settings import SettingsPage

_SIDEBAR_ITEMS = [
    "Dashboard",
    "Projects Setup",
    "Input",
    "Image Validation",
    "COLMAP",
    "Reconstruction",
    "LichtFeld",
    "Training",
    "Cleanup",
    "Export",
    "Render",
    "Logs",
    "Settings",
]

# Pages implemented in phase01 + phase02 + phase03. Anything else in the
# sidebar is shown as a "coming soon" placeholder so the full navigation
# is visible without pretending later phases already work.
_IMPLEMENTED_PAGES = {
    "Dashboard",
    "Projects Setup",
    "Input",
    "Image Validation",
    "Logs",
    "Settings",
}


class PlaceholderPage(QWidget):
    def __init__(self, page_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QLabel

        layout = QVBoxLayout(self)
        title = QLabel(page_name)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        note = QLabel(f"{page_name} is implemented in a later development phase.")
        note.setObjectName("statusMuted")
        layout.addWidget(note)
        layout.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.logger = get_app_logger()
        self.config_manager = ConfigManager()
        self.project_manager = ProjectManager(self.config_manager)

        self.setWindowTitle("Local 3DGS Studio")
        self.setMinimumSize(1200, 750)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        for name in _SIDEBAR_ITEMS:
            QListWidgetItem(name, self.sidebar)
        self.sidebar.currentRowChanged.connect(self._on_sidebar_row_changed)
        root_layout.addWidget(self.sidebar)

        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(24, 24, 24, 24)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        root_layout.addWidget(content_container, stretch=1)

        self._page_index_by_name: dict[str, int] = {}
        self.dashboard_page = DashboardPage(self.project_manager)
        self.projects_setup_page = ProjectsSetupPage(self.project_manager)
        self.projects_setup_page.project_created.connect(self._on_project_changed)
        self.input_page = InputPage(self.project_manager)
        self.image_validation_page = ImageValidationPage(self.project_manager)
        self.input_page.on_navigate_to_validation = lambda: self.sidebar.setCurrentRow(
            self._page_index_by_name["Image Validation"]
        )
        self.logs_page = LogsPage(self.project_manager)
        self.settings_page = SettingsPage(self.config_manager)

        page_widgets = {
            "Dashboard": self.dashboard_page,
            "Projects Setup": self.projects_setup_page,
            "Input": self.input_page,
            "Image Validation": self.image_validation_page,
            "Logs": self.logs_page,
            "Settings": self.settings_page,
        }

        for name in _SIDEBAR_ITEMS:
            widget = page_widgets.get(name) or PlaceholderPage(name)
            index = self.stack.addWidget(widget)
            self._page_index_by_name[name] = index

        self._add_open_project_action(root_layout)

        self.sidebar.setCurrentRow(0)
        self._attempt_load_last_project()

    def _add_open_project_action(self, root_layout: QHBoxLayout) -> None:
        """A persistent 'Open Project' entry point, reachable regardless
        of which sidebar page is showing, per 'user should only select a
        project folder'. Wraps the sidebar list and this button into one
        fixed-width column."""
        open_button = QPushButton("Open Project...")
        open_button.setObjectName("secondaryButton")
        open_button.clicked.connect(self._open_project_dialog)

        index = root_layout.indexOf(self.sidebar)
        root_layout.removeWidget(self.sidebar)
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)
        column_layout.addWidget(self.sidebar, stretch=1)
        column_layout.addWidget(open_button)
        column.setFixedWidth(200)
        root_layout.insertWidget(index, column)

    def _on_sidebar_row_changed(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        current_widget = self.stack.currentWidget()
        if current_widget is self.dashboard_page:
            self.dashboard_page.refresh()
        elif current_widget is self.input_page:
            self.input_page.refresh()
        elif current_widget is self.image_validation_page:
            self.image_validation_page.refresh()

    def _open_project_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Project Folder")
        if not folder:
            return
        try:
            self.project_manager.open_project(folder)
        except ProjectLoadError as exc:
            QMessageBox.critical(self, "Could Not Open Project", str(exc))
            return
        self._on_project_changed()

    def _on_project_changed(self) -> None:
        self.dashboard_page.refresh()
        self.input_page.refresh()
        self.image_validation_page.refresh()
        self.logs_page._reload()  # noqa: SLF001 - internal refresh on project switch
        self.sidebar.setCurrentRow(self._page_index_by_name["Dashboard"])

    def _attempt_load_last_project(self) -> None:
        last_root = self.config_manager.load_last_project()
        if last_root is None:
            self.logger.info("No previously opened project found.")
            return

        if not last_root.exists():
            self.logger.warning("Last opened project folder is missing: %s", last_root)
            self._show_missing_project_prompt(str(last_root))
            return

        try:
            self.project_manager.open_project(str(last_root))
        except ProjectLoadError as exc:
            self.logger.error("Last opened project is invalid: %s", exc)
            self._show_invalid_project_prompt(str(exc))
            return

        self.logger.info("Automatically reopened last project: %s", last_root)
        self.dashboard_page.refresh()
        self.input_page.refresh()
        self.image_validation_page.refresh()

    def _show_missing_project_prompt(self, missing_path: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Project Not Found")
        box.setText(
            "The last opened project could not be found:\n"
            f"{missing_path}"
        )
        open_button = box.addButton("Open Project", QMessageBox.ButtonRole.ActionRole)
        setup_button = box.addButton("Projects Setup", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Continue Without Project", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            self._open_project_dialog()
        elif box.clickedButton() is setup_button:
            self.sidebar.setCurrentRow(self._page_index_by_name["Projects Setup"])

    def _show_invalid_project_prompt(self, error_message: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Invalid Project")
        box.setText(f"The last opened project could not be loaded:\n{error_message}")
        open_button = box.addButton("Open Another Project", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Continue Without Project", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            self._open_project_dialog()
