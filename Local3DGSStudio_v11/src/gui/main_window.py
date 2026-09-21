"""Main application window: a minimal, professional DCC-style shell.

Nothing in this file computes project state, runs external processes, or
touches project.json directly -- it only arranges and refreshes the
existing page widgets, every one of which owns 100% of its own logic.
Per the v04 redesign: no traditional main menu bar and no separate
toolbar (their actions either live inside the relevant workspace already
-- COLMAP's own Run/Stop controls, LichtFeld's own Prepare Scene/Open
buttons -- or are contextual to Dashboard -- New/Open Project). The
sidebar is the only persistent navigation: a pinned Dashboard entry plus
a WORKFLOW section, each item icon-labeled and status-indicator-prefixed
from already-persisted state (never recomputed here). A slim top bar
shows read-only project/workspace context. The bottom console
(``LogsPage``, unchanged, re-hosted in a dock restricted to the bottom
area only) and settings (``SettingsPage``, unchanged, in a dialog opened
from a small corner button) round out the shell.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.config_manager import ConfigManager
from src.core.hardware_monitor import read_system_info
from src.core.logger import get_app_logger
from src.core.project_manager import ProjectLoadError, ProjectManager
from src.core.reconstruction_qc import QCResult
from src.gui.colmap_panel import ColmapPanel
from src.gui.dashboard import DashboardPage
from src.gui.icons import workflow_icon
from src.gui.image_validation import ImageValidationPage
from src.gui.image_workspace import ImageWorkspace
from src.gui.input_panel import InputPage
from src.gui.lichtfeld_panel import LichtFeldPage
from src.gui.logs import LogsPage
from src.gui.projects_setup import ProjectsSetupPage
from src.gui.reconstruction_qc_panel import ReconstructionQCPage
from src.gui.reconstruction_workspace import ReconstructionWorkspace
from src.gui.settings import SettingsPage

# Pinned above the "WORKFLOW" section.
_TOP_NAV_ITEMS = ["Dashboard"]

# Image and Image Validation are combined into one workspace ("Image").
_WORKFLOW_ITEMS = [
    "Image",
    "COLMAP",
    "Reconstruction",
    "LichtFeld",
    "Training",
    "Cleanup",
]

# A small, visually muted "not yet available" section beneath WORKFLOW.
_FUTURE_ITEMS = ["Render", "Export"]

# Reachable only from Dashboard's contextual "New Project" action -- not
# part of any persistent nav list.
_NON_NAV_PAGES = ["Projects Setup"]

_ALL_PAGE_NAMES = _TOP_NAV_ITEMS + _WORKFLOW_ITEMS + _FUTURE_ITEMS + _NON_NAV_PAGES

_SIDEBAR_ICON_IDS = {
    "Dashboard": "dashboard",
    "Image": "image",
    "COLMAP": "camera",
    "Reconstruction": "pointCloud",
    "LichtFeld": "gaussian",
    "Training": "training",
    "Cleanup": "cleanup",
    "Render": "render",
    "Export": "export",
}

_LOG_FILE_BY_LABEL = {
    "Application Log": "application.log",
    "COLMAP Log": "colmap.log",
    "LichtFeld Log": "lichtfeld.log",
    "Training Log": "training.log",
}

# Status-indicator symbols. Direct text-mappings of already-persisted
# state strings, never a recomputation -- "do not calculate workflow
# state separately" in the sidebar.
_SYMBOL_READY = "\u25cf"    # ●
_SYMBOL_WARNING = "\u25d0"  # ◐
_SYMBOL_NEUTRAL = "\u25cb"  # ○


class PlaceholderPage(QWidget):
    def __init__(self, page_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
        self._syncing_nav = False

        self.setWindowTitle("Local 3DGS Studio")
        self.setMinimumSize(1280, 800)

        self._build_pages()
        self._build_top_bar()
        self._build_central_widget()
        self._build_console_dock()
        self._build_shortcuts()

        self._activate_page("Dashboard")
        self._attempt_load_last_project()

        self._hardware_timer = QTimer(self)
        self._hardware_timer.setInterval(3000)
        self._hardware_timer.timeout.connect(self._update_top_bar)
        self._hardware_timer.start()

    # -- construction -----------------------------------------------------------

    def _build_pages(self) -> None:
        self.dashboard_page = DashboardPage(self.project_manager)
        self.dashboard_page.new_project_requested.connect(lambda: self._activate_page("Projects Setup"))
        self.dashboard_page.open_project_requested.connect(self._open_project_dialog)

        self.projects_setup_page = ProjectsSetupPage(self.project_manager)
        self.projects_setup_page.project_created.connect(self._on_project_changed)

        self.input_page = InputPage(self.project_manager)
        self.image_validation_page = ImageValidationPage(self.project_manager)
        self.image_workspace = ImageWorkspace(self.input_page, self.image_validation_page)

        self.colmap_page = ColmapPanel(self.project_manager, self.config_manager)
        self.reconstruction_qc_page = ReconstructionQCPage(self.project_manager, self.config_manager)
        self.reconstruction_workspace = ReconstructionWorkspace(
            self.reconstruction_qc_page, self.project_manager
        )
        self.lichtfeld_page = LichtFeldPage(self.project_manager, self.config_manager)
        self.colmap_page.pipeline_finished.connect(self.reconstruction_qc_page.run_qc)
        self.colmap_page.pipeline_finished.connect(self.lichtfeld_page.refresh)
        self.colmap_page.pipeline_finished.connect(self._update_top_bar)

        # Logs and Settings are not workspace pages -- Logs is re-hosted
        # in the bottom console dock, Settings in a dialog opened from a
        # small corner button. The underlying widgets are unchanged.
        self.logs_page = LogsPage(self.project_manager)
        self.settings_page = SettingsPage(self.config_manager)

        self._page_widgets: dict[str, QWidget] = {
            "Dashboard": self.dashboard_page,
            "Projects Setup": self.projects_setup_page,
            "Image": self.image_workspace,
            "COLMAP": self.colmap_page,
            "Reconstruction": self.reconstruction_workspace,
            "LichtFeld": self.lichtfeld_page,
        }

    def _build_top_bar(self) -> None:
        self.top_bar = QWidget()
        self.top_bar.setObjectName("topBar")
        layout = QHBoxLayout(self.top_bar)
        layout.setContentsMargins(14, 6, 10, 6)
        self.top_bar_label = QLabel("Local 3DGS Studio")
        self.top_bar_label.setObjectName("topBarLabel")
        layout.addWidget(self.top_bar_label)
        layout.addStretch(1)
        settings_button = QPushButton("\u2699")  # gear
        settings_button.setObjectName("consoleToggleButton")
        settings_button.setFixedWidth(28)
        settings_button.setToolTip("Settings")
        settings_button.clicked.connect(self._open_settings_dialog)
        layout.addWidget(settings_button)

    def _build_central_widget(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.top_bar)

        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(self.body_splitter, stretch=1)

        sidebar_column = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_column)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self.top_nav = QListWidget()
        self.top_nav.setObjectName("workflowSidebar")
        for name in _TOP_NAV_ITEMS:
            item = QListWidgetItem(workflow_icon(_SIDEBAR_ICON_IDS[name]), name)
            self.top_nav.addItem(item)
        self.top_nav.setFixedHeight(40)
        self.top_nav.currentRowChanged.connect(
            lambda row: self._on_nav_row_changed(row, _TOP_NAV_ITEMS)
        )
        sidebar_layout.addWidget(self.top_nav)

        workflow_label = QLabel("WORKFLOW")
        workflow_label.setObjectName("sectionLabel")
        workflow_label.setContentsMargins(14, 10, 0, 2)
        sidebar_layout.addWidget(workflow_label)

        self.workflow_nav = QListWidget()
        self.workflow_nav.setObjectName("workflowSidebar")
        for name in _WORKFLOW_ITEMS:
            item = QListWidgetItem(
                workflow_icon(_SIDEBAR_ICON_IDS[name]), f"{_SYMBOL_NEUTRAL} {name}"
            )
            self.workflow_nav.addItem(item)
        self.workflow_nav.currentRowChanged.connect(
            lambda row: self._on_nav_row_changed(row, _WORKFLOW_ITEMS)
        )
        sidebar_layout.addWidget(self.workflow_nav, stretch=1)

        future_label = QLabel("FUTURE")
        future_label.setObjectName("statusMuted")
        future_label.setContentsMargins(14, 6, 0, 2)
        sidebar_layout.addWidget(future_label)

        self.future_nav = QListWidget()
        self.future_nav.setObjectName("workflowSidebar")
        for name in _FUTURE_ITEMS:
            item = QListWidgetItem(workflow_icon(_SIDEBAR_ICON_IDS[name]), name)
            self.future_nav.addItem(item)
        self.future_nav.setFixedHeight(72)
        self.future_nav.currentRowChanged.connect(
            lambda row: self._on_nav_row_changed(row, _FUTURE_ITEMS)
        )
        sidebar_layout.addWidget(self.future_nav)

        sidebar_column.setFixedWidth(220)
        self.body_splitter.addWidget(sidebar_column)

        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(24, 20, 24, 20)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        self.body_splitter.addWidget(content_container)
        self.body_splitter.setStretchFactor(1, 1)

        self._page_index_by_name: dict[str, int] = {}
        for name in _ALL_PAGE_NAMES:
            widget = self._page_widgets.get(name) or PlaceholderPage(name)
            index = self.stack.addWidget(widget)
            self._page_index_by_name[name] = index

    def _build_console_dock(self) -> None:
        """The bottom-only, collapsible console: ``LogsPage`` re-hosted
        in a ``QDockWidget`` restricted to the bottom dock area (per the
        redesign's "console must only dock at the bottom" rule)."""
        self.console_dock = QDockWidget("Console", self)
        self.console_dock.setObjectName("consoleDock")
        self.console_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.console_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("consoleHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 4, 6, 4)
        header_label = QLabel("CONSOLE")
        header_label.setObjectName("consoleHeaderLabel")
        header_layout.addWidget(header_label)
        header_layout.addStretch(1)
        self._console_toggle_button = QPushButton("\u25be")  # collapse arrow
        self._console_toggle_button.setObjectName("consoleToggleButton")
        self._console_toggle_button.setFixedWidth(24)
        self._console_toggle_button.clicked.connect(self._toggle_console)
        header_layout.addWidget(self._console_toggle_button)
        container_layout.addWidget(header)

        container_layout.addWidget(self.logs_page, stretch=1)

        self.console_dock.setWidget(container)
        self.console_dock.setMinimumHeight(36)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.console_dock)
        self.resizeDocks([self.console_dock], [220], Qt.Orientation.Vertical)
        self._console_collapsed = False

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self._activate_page("Projects Setup"))
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._open_project_dialog)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save_project)
        QShortcut(QKeySequence("F5"), self, activated=self._refresh_current_page)
        QShortcut(QKeySequence("Esc"), self, activated=self._on_escape)

    # -- navigation ---------------------------------------------------------------

    def _on_nav_row_changed(self, row: int, names: list[str]) -> None:
        if self._syncing_nav or row < 0:
            return
        self._activate_page(names[row])

    def _activate_page(self, name: str) -> None:
        index = self._page_index_by_name.get(name)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self._sync_nav_selection(name)
        self._refresh_page(name)
        self._update_top_bar()

    def _activate_reconstruction_tab(self, index: int) -> None:
        self._activate_page("Reconstruction")
        self.reconstruction_workspace.tabs.setCurrentIndex(index)

    def _sync_nav_selection(self, name: str) -> None:
        self._syncing_nav = True
        try:
            self.top_nav.setCurrentRow(_TOP_NAV_ITEMS.index(name) if name in _TOP_NAV_ITEMS else -1)
            self.workflow_nav.setCurrentRow(
                _WORKFLOW_ITEMS.index(name) if name in _WORKFLOW_ITEMS else -1
            )
            self.future_nav.setCurrentRow(_FUTURE_ITEMS.index(name) if name in _FUTURE_ITEMS else -1)
        finally:
            self._syncing_nav = False

    def _refresh_page(self, name: str) -> None:
        widget = self._page_widgets.get(name)
        if widget is not None and hasattr(widget, "refresh"):
            widget.refresh()

    def _refresh_current_page(self) -> None:
        for name, index in self._page_index_by_name.items():
            if index == self.stack.currentIndex():
                self._refresh_page(name)
                return

    def _on_escape(self) -> None:
        if self.colmap_page._running_full_pipeline:  # noqa: SLF001
            self.colmap_page._on_stop_clicked()  # noqa: SLF001 - existing action

    # -- console --------------------------------------------------------------------

    def _toggle_console(self) -> None:
        self._console_collapsed = not self._console_collapsed
        self.logs_page.setVisible(not self._console_collapsed)
        self._console_toggle_button.setText("\u25b8" if self._console_collapsed else "\u25be")

    def _show_console_log(self, label: str) -> None:
        filename = _LOG_FILE_BY_LABEL.get(label)
        if filename is None:
            return
        if self._console_collapsed:
            self._toggle_console()
        self.console_dock.setVisible(True)
        index = self.logs_page.log_selector.findText(filename)
        if index >= 0:
            self.logs_page.log_selector.setCurrentIndex(index)
        self.logs_page._reload()  # noqa: SLF001 - internal refresh, same page, no logic change

    def _open_log_folder(self) -> None:
        if self.project_manager.current is None:
            return
        path = self.project_manager.current.resolver.logs
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # -- settings dialog --------------------------------------------------------------

    def _open_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setMinimumSize(560, 480)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.settings_page)
        dialog.exec()
        # Re-parent the (unchanged) settings page back so it's ready to
        # reuse the next time the dialog opens.
        content_container = self.stack.parentWidget()
        content_container.layout().addWidget(self.settings_page)
        self.settings_page.hide()

    # -- top bar / sidebar indicators ----------------------------------------------

    def _workflow_status_symbol(self, name: str) -> str:
        """Reads already-persisted state only -- never recomputes QC,
        validation, or COLMAP status."""
        current = self.project_manager.current
        if current is None:
            return _SYMBOL_NEUTRAL

        if name == "Image":
            status = current.data.validation_info.get("validationStatus", "")
            if status == "VALID":
                return _SYMBOL_READY
            if status == "WARNING":
                return _SYMBOL_WARNING
            return _SYMBOL_NEUTRAL

        if name == "COLMAP":
            completed = bool(current.data.colmap_info.get("analysis", {}).get("completed"))
            return _SYMBOL_READY if completed else _SYMBOL_NEUTRAL

        if name == "Reconstruction":
            state = current.data.reconstruction_qc_info.get("state", "NOT_READY")
            return {"READY": _SYMBOL_READY, "WARNING": _SYMBOL_WARNING}.get(state, _SYMBOL_NEUTRAL)

        if name == "LichtFeld":
            result = QCResult.from_project_json_dict(current.data.reconstruction_qc_info)
            return _SYMBOL_READY if result.is_ready_for_lichtfeld else _SYMBOL_NEUTRAL

        return _SYMBOL_NEUTRAL

    def _update_workflow_indicators(self) -> None:
        for i, name in enumerate(_WORKFLOW_ITEMS):
            symbol = self._workflow_status_symbol(name)
            self.workflow_nav.item(i).setText(f"{symbol} {name}")

    def _update_top_bar(self) -> None:
        current = self.project_manager.current
        current_workspace = ""
        for name, index in self._page_index_by_name.items():
            if index == self.stack.currentIndex():
                current_workspace = name
                break

        if current is None:
            self.top_bar_label.setText("Local 3DGS Studio  |  No project open")
        else:
            qc_state = current.data.reconstruction_qc_info.get("state", "NOT_READY")
            self.top_bar_label.setText(
                f"Local 3DGS Studio  |  {current.data.name}  |  {current.data.version}  |  "
                f"{current_workspace}  |  {qc_state}"
            )

        self._update_workflow_indicators()

    # Backward-compatible alias (older tests/callers may still expect
    # this name from before the top-bar-replaces-status-bar change).
    _update_status_bar = _update_top_bar

    # -- project lifecycle (unchanged behavior from before the redesign) ------------

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

    def _save_project(self) -> None:
        if self.project_manager.current is None:
            return
        try:
            self.project_manager.save_project_json()
        except ProjectLoadError as exc:
            QMessageBox.critical(self, "Could Not Save Project", str(exc))
            return
        self._update_top_bar()

    def _on_project_changed(self) -> None:
        for name in _TOP_NAV_ITEMS + _WORKFLOW_ITEMS:
            self._refresh_page(name)
        self.logs_page._reload()  # noqa: SLF001 - internal refresh on project switch
        self._activate_page("Dashboard")

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
        for name in _TOP_NAV_ITEMS + _WORKFLOW_ITEMS:
            self._refresh_page(name)
        self._update_top_bar()

    def _show_missing_project_prompt(self, missing_path: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Project Not Found")
        box.setText(f"The last opened project could not be found:\n{missing_path}")
        open_button = box.addButton("Open Project", QMessageBox.ButtonRole.ActionRole)
        setup_button = box.addButton("Projects Setup", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Continue Without Project", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            self._open_project_dialog()
        elif box.clickedButton() is setup_button:
            self._activate_page("Projects Setup")

    def _show_invalid_project_prompt(self, error_message: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Invalid Project")
        box.setText(f"The last opened project could not be loaded:\n{error_message}")
        open_button = box.addButton("Open Another Project", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Continue Without Project", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            self._open_project_dialog()
