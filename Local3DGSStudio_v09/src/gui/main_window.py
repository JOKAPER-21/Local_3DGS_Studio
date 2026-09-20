"""Main application window: a professional, Blender-inspired shell around
the existing pages.

Nothing in this file computes project state, runs external processes, or
touches project.json directly -- it only arranges and refreshes the
existing page widgets (``DashboardPage``, ``ProjectsSetupPage``,
``InputPage``, ``ImageValidationPage``, ``ColmapPanel``,
``ReconstructionQCPage`` (embedded in ``ReconstructionWorkspace``),
``LichtFeldPage``, ``LogsPage``, ``SettingsPage``), every one of which is
unchanged from before this redesign and still owns 100% of its own
logic. This is purely a shell change: menu bar, a main toolbar, a
two-part sidebar (pinned actions + a "WORKFLOW" section with persisted-
state status indicators), a central workspace, a collapsible bottom
console (``LogsPage`` re-hosted in a dock instead of a full page), and a
status bar -- plus the same startup sequence as before
(readLastProjectConfiguration -> checkProjectExists -> validateProjectJson
-> loadProject -> resolveProjectPaths -> refreshDashboard).
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
from src.gui.image_validation import ImageValidationPage
from src.gui.input_panel import InputPage
from src.gui.lichtfeld_panel import LichtFeldPage
from src.gui.logs import LogsPage
from src.gui.projects_setup import ProjectsSetupPage
from src.gui.reconstruction_qc_panel import ReconstructionQCPage
from src.gui.reconstruction_workspace import ReconstructionWorkspace
from src.gui.settings import SettingsPage

# Pinned above the "WORKFLOW" section -- project-level actions rather
# than pipeline stages.
_TOP_NAV_ITEMS = ["Dashboard", "Projects Setup"]

# The Blender-inspired vertical workflow list. Logs and Settings live in
# the menu bar / console dock (see below); Render lives under the
# "Render" menu, not the workflow list.
_WORKFLOW_ITEMS = [
    "Input",
    "Image Validation",
    "COLMAP",
    "Reconstruction",
    "LichtFeld",
    "Training",
    "Cleanup",
]

# Reachable via menus only (File > Export, Render > *), not the sidebar.
_MENU_ONLY_ITEMS = ["Export", "Render"]

_ALL_PAGE_NAMES = _TOP_NAV_ITEMS + _WORKFLOW_ITEMS + _MENU_ONLY_ITEMS

_LOG_FILE_BY_MENU_LABEL = {
    "Application Log": "application.log",
    "COLMAP Log": "colmap.log",
    "LichtFeld Log": "lichtfeld.log",
    "Training Log": "training.log",
}

# Sidebar/status-indicator symbols. Never a fourth "FAILED-specific"
# glyph -- keeping the set small matches the sidebar spec's "do not
# calculate workflow state separately" rule: these are direct
# text-mappings of already-persisted state strings, not judgments.
_SYMBOL_READY = "\u25cf"    # ●
_SYMBOL_WARNING = "\u25d0"  # ◐
_SYMBOL_NEUTRAL = "\u25cb"  # ○

_COLMAP_STEP_LABELS = {
    "Feature Extraction": "Features",
    "Feature Matching": "Matching",
    "Mapper": "Mapper",
    "Model Analysis": "Analysis",
}


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
        self._build_menu_bar()
        self._build_toolbar()
        self._build_central_widget()
        self._build_console_dock()
        self._build_status_bar()
        self._build_shortcuts()

        self._activate_page("Dashboard")
        self._attempt_load_last_project()

        self._hardware_timer = QTimer(self)
        self._hardware_timer.setInterval(3000)
        self._hardware_timer.timeout.connect(self._update_status_bar)
        self._hardware_timer.start()

    # -- construction -----------------------------------------------------------

    def _build_pages(self) -> None:
        self.dashboard_page = DashboardPage(self.project_manager)
        self.projects_setup_page = ProjectsSetupPage(self.project_manager)
        self.projects_setup_page.project_created.connect(self._on_project_changed)
        self.input_page = InputPage(self.project_manager)
        self.image_validation_page = ImageValidationPage(self.project_manager)
        self.input_page.on_navigate_to_validation = lambda: self._activate_page("Image Validation")
        self.colmap_page = ColmapPanel(self.project_manager, self.config_manager)
        self.reconstruction_qc_page = ReconstructionQCPage(self.project_manager, self.config_manager)
        self.reconstruction_workspace = ReconstructionWorkspace(
            self.reconstruction_qc_page, self.project_manager
        )
        self.lichtfeld_page = LichtFeldPage(self.project_manager, self.config_manager)
        self.colmap_page.pipeline_finished.connect(self.reconstruction_qc_page.run_qc)
        self.colmap_page.pipeline_finished.connect(self.lichtfeld_page.refresh)
        self.colmap_page.pipeline_finished.connect(self._update_status_bar)

        # Logs and Settings are no longer full workspace pages -- Logs is
        # re-hosted in the bottom console dock, Settings in a dialog. The
        # underlying widgets (and every signal/behavior they have) are
        # unchanged.
        self.logs_page = LogsPage(self.project_manager)
        self.settings_page = SettingsPage(self.config_manager)

        self._page_widgets: dict[str, QWidget] = {
            "Dashboard": self.dashboard_page,
            "Projects Setup": self.projects_setup_page,
            "Input": self.input_page,
            "Image Validation": self.image_validation_page,
            "COLMAP": self.colmap_page,
            "Reconstruction": self.reconstruction_workspace,
            "LichtFeld": self.lichtfeld_page,
        }

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        new_project_action = file_menu.addAction("New Project")
        new_project_action.setShortcut(QKeySequence("Ctrl+N"))
        new_project_action.triggered.connect(lambda: self._activate_page("Projects Setup"))
        open_project_action = file_menu.addAction("Open Project")
        open_project_action.setShortcut(QKeySequence("Ctrl+O"))
        open_project_action.triggered.connect(self._open_project_dialog)
        file_menu.addAction("Project Setup").triggered.connect(
            lambda: self._activate_page("Projects Setup")
        )
        save_project_action = file_menu.addAction("Save Project")
        save_project_action.setShortcut(QKeySequence("Ctrl+S"))
        save_project_action.triggered.connect(self._save_project)
        file_menu.addAction("Export").triggered.connect(lambda: self._activate_page("Export"))
        file_menu.addSeparator()
        file_menu.addAction("Exit").triggered.connect(self.close)

        workflow_menu = menu_bar.addMenu("&Workflow")
        workflow_menu.addAction("Input").triggered.connect(lambda: self._activate_page("Input"))
        workflow_menu.addAction("Image Validation").triggered.connect(
            lambda: self._activate_page("Image Validation")
        )

        colmap_menu = workflow_menu.addMenu("COLMAP")
        for label in ("Feature Extraction", "Feature Matching", "Mapper", "Model Analysis"):
            colmap_menu.addAction(label).triggered.connect(
                lambda checked=False, lbl=label: self._run_colmap_step(lbl)
            )
        colmap_menu.addSeparator()
        colmap_menu.addAction("Run Pipeline").triggered.connect(self._on_toolbar_run)
        colmap_menu.addAction("Stop").triggered.connect(self._on_toolbar_stop)

        reconstruction_menu = workflow_menu.addMenu("Reconstruction")
        reconstruction_menu.addAction("Overview").triggered.connect(
            lambda: self._activate_reconstruction_tab(0)
        )
        reconstruction_menu.addAction("Quality Control").triggered.connect(
            lambda: self._activate_reconstruction_tab(0)
        )
        reconstruction_menu.addAction("Sparse Point Cloud").triggered.connect(
            lambda: self._activate_reconstruction_tab(1)
        )
        reconstruction_menu.addAction("Camera Poses").triggered.connect(
            lambda: self._activate_reconstruction_tab(2)
        )

        lichtfeld_menu = workflow_menu.addMenu("LichtFeld")
        lichtfeld_menu.addAction("Prepare Scene").triggered.connect(self._on_menu_prepare_scene)
        lichtfeld_menu.addAction("Open in LichtFeld").triggered.connect(self._on_menu_open_lichtfeld)
        lichtfeld_menu.addAction("Scene Information").triggered.connect(
            lambda: self._activate_page("LichtFeld")
        )

        training_menu = workflow_menu.addMenu("Training")
        for label in ("Training Setup", "Start", "Pause", "Resume", "Stop"):
            training_menu.addAction(label).triggered.connect(lambda: self._activate_page("Training"))

        cleanup_menu = workflow_menu.addMenu("Cleanup")
        for label in ("Inspect", "Density Analysis", "Preview Changes", "Apply Cleanup"):
            cleanup_menu.addAction(label).triggered.connect(lambda: self._activate_page("Cleanup"))

        render_menu = menu_bar.addMenu("&Render")
        for label in ("New Render", "Render Settings", "Render History"):
            render_menu.addAction(label).triggered.connect(lambda: self._activate_page("Render"))

        logs_menu = menu_bar.addMenu("&Logs")
        for label in ("Application Log", "COLMAP Log", "LichtFeld Log", "Training Log"):
            logs_menu.addAction(label).triggered.connect(
                lambda checked=False, lbl=label: self._show_console_log(lbl)
            )
        logs_menu.addSeparator()
        logs_menu.addAction("Open Log Folder").triggered.connect(self._open_log_folder)

        settings_menu = menu_bar.addMenu("&Settings")
        # All four items open the same settings dialog for now -- this
        # application only has one implemented settings surface
        # (external software paths + default project root). Splitting
        # it into distinct General/Software Paths/Performance/Appearance
        # panels is future work, not something to fabricate here.
        for label in ("General", "Software Paths", "Performance", "Appearance"):
            settings_menu.addAction(label).triggered.connect(self._open_settings_dialog)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)

        toolbar.addAction("New Project").triggered.connect(
            lambda: self._activate_page("Projects Setup")
        )
        toolbar.addAction("Open Project").triggered.connect(self._open_project_dialog)
        toolbar.addAction("Save Project").triggered.connect(self._save_project)
        self.toolbar_run_action = toolbar.addAction("Run")
        self.toolbar_run_action.triggered.connect(self._on_toolbar_run)
        self.toolbar_stop_action = toolbar.addAction("Stop")
        self.toolbar_stop_action.triggered.connect(self._on_toolbar_stop)
        self.toolbar_stop_action.setEnabled(False)
        toolbar.addAction("Refresh").triggered.connect(self._refresh_current_page)
        toolbar.addAction("Open Console").triggered.connect(self._open_console)

    def _build_central_widget(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(self.body_splitter, stretch=1)

        sidebar_column = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_column)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self.top_nav = QListWidget()
        self.top_nav.setObjectName("workflowSidebar")
        for name in _TOP_NAV_ITEMS:
            QListWidgetItem(name, self.top_nav)
        self.top_nav.setFixedHeight(64)
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
            QListWidgetItem(f"{_SYMBOL_NEUTRAL} {name}", self.workflow_nav)
        self.workflow_nav.currentRowChanged.connect(
            lambda row: self._on_nav_row_changed(row, _WORKFLOW_ITEMS)
        )
        sidebar_layout.addWidget(self.workflow_nav, stretch=1)

        open_button = QPushButton("Open Project...")
        open_button.setObjectName("secondaryButton")
        open_button.clicked.connect(self._open_project_dialog)
        sidebar_layout.addWidget(open_button)

        sidebar_column.setFixedWidth(200)
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
        """The bottom collapsible console: LogsPage re-hosted in a
        QDockWidget instead of a full page. Its content (log selector,
        live tailing) is entirely unchanged -- only its container is
        new. (The v02 spec's per-tool console "tabs" are covered by the
        page's existing log-file selector rather than a second tab
        strip -- one selector, same underlying files, no duplicated
        tailing logic.)"""
        self.console_dock = QDockWidget("Console", self)
        self.console_dock.setObjectName("consoleDock")
        self.console_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

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

    def _build_status_bar(self) -> None:
        status_bar = self.statusBar()
        self.status_left_label = QLabel("No project open")
        self.status_right_label = QLabel("")
        status_bar.addWidget(self.status_left_label, stretch=1)
        status_bar.addPermanentWidget(self.status_right_label)
        self._update_status_bar()

    def _build_shortcuts(self) -> None:
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
        self._update_status_bar()

    def _activate_reconstruction_tab(self, index: int) -> None:
        self._activate_page("Reconstruction")
        self.reconstruction_workspace.tabs.setCurrentIndex(index)

    def _sync_nav_selection(self, name: str) -> None:
        self._syncing_nav = True
        try:
            if name in _TOP_NAV_ITEMS:
                self.top_nav.setCurrentRow(_TOP_NAV_ITEMS.index(name))
                self.workflow_nav.setCurrentRow(-1)
            elif name in _WORKFLOW_ITEMS:
                self.workflow_nav.setCurrentRow(_WORKFLOW_ITEMS.index(name))
                self.top_nav.setCurrentRow(-1)
            else:
                self.top_nav.setCurrentRow(-1)
                self.workflow_nav.setCurrentRow(-1)
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

    def _run_colmap_step(self, menu_label: str) -> None:
        step = _COLMAP_STEP_LABELS.get(menu_label)
        if step is None:
            return
        self._activate_page("COLMAP")
        self.colmap_page.step_selector.setCurrentText(step)
        self.colmap_page._on_run_selected_step()  # noqa: SLF001 - existing action

    def _on_toolbar_run(self) -> None:
        self.colmap_page._on_run_full_pipeline()  # noqa: SLF001 - existing action
        self._update_status_bar()

    def _on_toolbar_stop(self) -> None:
        self.colmap_page._on_stop_clicked()  # noqa: SLF001 - existing action
        self._update_status_bar()

    def _on_menu_prepare_scene(self) -> None:
        self._activate_page("LichtFeld")
        self.lichtfeld_page._on_prepare_scene()  # noqa: SLF001 - existing action

    def _on_menu_open_lichtfeld(self) -> None:
        self._activate_page("LichtFeld")
        self.lichtfeld_page._on_open_in_lichtfeld()  # noqa: SLF001 - existing action

    # -- console --------------------------------------------------------------------

    def _toggle_console(self) -> None:
        self._console_collapsed = not self._console_collapsed
        self.logs_page.setVisible(not self._console_collapsed)
        self._console_toggle_button.setText("\u25b8" if self._console_collapsed else "\u25be")

    def _open_console(self) -> None:
        if self._console_collapsed:
            self._toggle_console()
        self.console_dock.setVisible(True)

    def _show_console_log(self, menu_label: str) -> None:
        filename = _LOG_FILE_BY_MENU_LABEL.get(menu_label)
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
        # reuse the next time the dialog opens (QDialog.exec parents it
        # to the dialog for the duration of the modal).
        content_container = self.stack.parentWidget()
        content_container.layout().addWidget(self.settings_page)
        self.settings_page.hide()

    # -- status bar / sidebar indicators ----------------------------------------------

    def _workflow_status_symbol(self, name: str) -> str:
        """Reads already-persisted state only -- never recomputes QC,
        validation, or COLMAP status. See the "do not calculate workflow
        state separately" sidebar rule."""
        current = self.project_manager.current
        if current is None:
            return _SYMBOL_NEUTRAL

        if name == "Input":
            return _SYMBOL_READY if current.data.input_info.get("imageCount", 0) > 0 else _SYMBOL_NEUTRAL

        if name == "Image Validation":
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

    def _update_status_bar(self) -> None:
        current = self.project_manager.current
        if current is None:
            self.status_left_label.setText("No project open")
        else:
            qc_state = current.data.reconstruction_qc_info.get("state", "NOT_READY")
            image_count = current.data.input_info.get("imageCount", 0)
            self.status_left_label.setText(
                f"Project: {current.data.name}    Version: {current.data.version}    "
                f"Images: {image_count}    Reconstruction: {qc_state}"
            )

        info = read_system_info(current.project_root if current else None)
        if info.gpu and info.gpu.available:
            gpu_text = (
                f"GPU: {info.gpu.name}    VRAM: {info.gpu.vram_used_mb / 1024:.1f} / "
                f"{info.gpu.vram_total_mb / 1024:.1f} GB"
            )
        else:
            gpu_text = "GPU: not detected"
        self.status_right_label.setText(
            f"{gpu_text}    RAM: {info.ram_used_gb:.1f} / {info.ram_total_gb:.1f} GB"
        )

        self._update_workflow_indicators()

        running = bool(self.colmap_page._running_full_pipeline)  # noqa: SLF001
        self.toolbar_run_action.setEnabled(not running)
        self.toolbar_stop_action.setEnabled(running)

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
            self.status_left_label.setText("No project open -- nothing to save.")
            return
        try:
            self.project_manager.save_project_json()
        except ProjectLoadError as exc:
            QMessageBox.critical(self, "Could Not Save Project", str(exc))
            return
        self._update_status_bar()

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
        self._update_status_bar()

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
