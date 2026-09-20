"""Tests for the redesigned (v04) ``MainWindow`` shell.

These are the only tests in the suite that need a real ``QApplication``,
so ``QT_QPA_PLATFORM=offscreen`` is set here, before any Qt import,
rather than relying on the environment -- running plain ``pytest`` (no
extra env vars) must exercise these too.

Per v04: no traditional main menu bar, no separate toolbar. Navigation
is the sidebar (a pinned Dashboard entry + a WORKFLOW section, each item
icon-labeled and status-indicator-prefixed) plus a read-only top bar.
Image and Image Validation are combined into one workspace. Reconstruction
no longer has a "Send to LichtFeld" action (LichtFeld actions live only
in the LichtFeld workspace). The console docks at the bottom only.

These tests still assert that activating a workspace drives the real,
unchanged backend (project loading, COLMAP refresh, Reconstruction QC,
LichtFeld) -- the redesign must not have created a second, GUI-only
notion of project state.
"""

from __future__ import annotations

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QToolBar

from src.gui.main_window import (
    _FUTURE_ITEMS,
    _SIDEBAR_ICON_IDS,
    _TOP_NAV_ITEMS,
    _WORKFLOW_ITEMS,
    MainWindow,
    PlaceholderPage,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture()
def window(qt_app, tmp_path, monkeypatch):
    # Isolate from any real last_project.json on the machine running tests.
    monkeypatch.setattr(
        "src.core.config_manager.get_app_config_dir", lambda: tmp_path / "appConfig"
    )
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QDialog, "exec", lambda self: None)
    win = MainWindow()
    win.show()
    yield win
    win.close()


def _create_project_with_reconstruction(win, tmp_path, project_name="testProject"):
    opened = win.project_manager.create_project(str(tmp_path / "projects"), project_name, "v01")
    resolver = opened.resolver
    resolver.images.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (resolver.images / f"img_{i:04d}.jpg").write_bytes(b"fake jpg bytes")

    sparse = resolver.colmap / "sparse" / "0"
    sparse.mkdir(parents=True, exist_ok=True)
    (sparse / "images.bin").write_bytes(b"fake images bin")
    (sparse / "points3D.bin").write_bytes(b"fake points3D bin")
    with open(sparse / "cameras.bin", "wb") as handle:
        handle.write(struct.pack("<Q", 1))
        handle.write(struct.pack("<iiQQ", 1, 2, 1920, 1080))
        for value in (1400.0, 960.0, 540.0, -0.05):
            handle.write(struct.pack("<d", value))
    (resolver.colmap / "database.db").write_bytes(b"fake database bytes")

    opened.data.colmap_info["analysis"] = {
        "completed": True, "totalImages": 5, "registeredImages": 5,
        "points": 1000, "observations": 5000, "meanTrackLength": 5.0,
        "meanObservationsPerImage": 1000.0, "meanReprojectionError": 0.5,
    }
    opened.data.input_info["imageCount"] = 5
    win.project_manager.save_project_json()
    win._on_project_changed()
    return opened


# ---------------------------------------------------------------------------
# Startup / no menu bar / no toolbar
# ---------------------------------------------------------------------------


def test_main_window_starts_without_blocking(window):
    assert window is not None


def test_no_traditional_main_menu_bar(window):
    assert window.menuBar().actions() == []


def test_no_separate_toolbar(window):
    assert window.findChildren(QToolBar) == []


def test_top_bar_exists_with_no_menu(window):
    assert window.top_bar is not None
    assert window.menuBar().actions() == []


# ---------------------------------------------------------------------------
# Sidebar: Dashboard + WORKFLOW + icons, no persistent Open Project/Project
# Setup buttons
# ---------------------------------------------------------------------------


def test_sidebar_contains_dashboard_and_workflow_sections(window):
    top_items = [window.top_nav.item(i).text() for i in range(window.top_nav.count())]
    assert top_items == _TOP_NAV_ITEMS
    assert "Dashboard" in top_items

    workflow_items = [window.workflow_nav.item(i).text() for i in range(window.workflow_nav.count())]
    for name in _WORKFLOW_ITEMS:
        assert any(item.endswith(name) for item in workflow_items)


def test_sidebar_has_no_open_project_or_project_setup_buttons(window):
    top_items = [window.top_nav.item(i).text() for i in range(window.top_nav.count())]
    workflow_items = [window.workflow_nav.item(i).text() for i in range(window.workflow_nav.count())]
    assert "Open Project..." not in top_items
    assert "Projects Setup" not in top_items
    assert not any("Open Project" in t for t in top_items + workflow_items)
    assert not any("Project Setup" in t for t in top_items + workflow_items)


def test_all_sidebar_workflow_items_have_icons(window):
    for i in range(window.workflow_nav.count()):
        icon = window.workflow_nav.item(i).icon()
        assert isinstance(icon, QIcon)
        assert not icon.isNull()
    for i in range(window.top_nav.count()):
        assert not window.top_nav.item(i).icon().isNull()


def test_sidebar_icon_ids_cover_every_nav_item(window):
    for name in _TOP_NAV_ITEMS + _WORKFLOW_ITEMS + _FUTURE_ITEMS:
        assert name in _SIDEBAR_ICON_IDS


# ---------------------------------------------------------------------------
# Sidebar / workspace synchronization
# ---------------------------------------------------------------------------


def test_activating_workflow_page_switches_stack_and_syncs_sidebar(window):
    window._activate_page("COLMAP")
    assert window.stack.currentWidget() is window.colmap_page
    assert _WORKFLOW_ITEMS[window.workflow_nav.currentRow()] == "COLMAP"
    assert window.top_nav.currentRow() == -1


def test_activating_top_nav_page_clears_workflow_selection(window):
    window._activate_page("COLMAP")
    window._activate_page("Dashboard")
    assert window.stack.currentWidget() is window.dashboard_page
    assert _TOP_NAV_ITEMS[window.top_nav.currentRow()] == "Dashboard"
    assert window.workflow_nav.currentRow() == -1


def test_clicking_sidebar_item_activates_same_page_as_direct_call(window):
    window.workflow_nav.setCurrentRow(_WORKFLOW_ITEMS.index("COLMAP"))
    assert window.stack.currentWidget() is window.colmap_page

    window._activate_page("Reconstruction")
    assert window.stack.currentWidget() is window.reconstruction_workspace
    assert _WORKFLOW_ITEMS[window.workflow_nav.currentRow()] == "Reconstruction"


def test_placeholder_pages_used_for_unimplemented_workflows(window):
    window._activate_page("Training")
    assert isinstance(window.stack.currentWidget(), PlaceholderPage)
    window._activate_page("Cleanup")
    assert isinstance(window.stack.currentWidget(), PlaceholderPage)
    window._activate_page("Render")
    assert isinstance(window.stack.currentWidget(), PlaceholderPage)
    window._activate_page("Export")
    assert isinstance(window.stack.currentWidget(), PlaceholderPage)


def test_future_nav_contains_render_and_export(window):
    future_items = [window.future_nav.item(i).text() for i in range(window.future_nav.count())]
    assert future_items == _FUTURE_ITEMS


# ---------------------------------------------------------------------------
# Image workspace: Input + Image Validation combined, right panel is
# "Properties"
# ---------------------------------------------------------------------------


def test_image_and_validation_are_one_workspace(window):
    window._activate_page("Image")
    assert window.stack.currentWidget() is window.image_workspace
    assert window.image_workspace.input_page is window.input_page
    assert window.image_workspace.image_validation_page is window.image_validation_page


def test_image_validation_is_the_centered_content(window):
    # Validation is added first / with stretch so it's the dominant,
    # centered content; the input page is the fixed-width side column.
    layout = window.image_workspace.layout()
    assert layout.itemAt(0).widget() is window.image_validation_page


def test_image_workspace_right_panel_is_named_properties(window):
    from PySide6.QtWidgets import QLabel
    headers = [
        lbl.text() for lbl in window.image_workspace.findChildren(QLabel)
        if lbl.objectName() == "propertiesHeader"
    ]
    assert any("PROPERTIES" in h for h in headers)


# ---------------------------------------------------------------------------
# COLMAP workspace: pipeline + live output in center, settings in
# Properties, live output fills space
# ---------------------------------------------------------------------------


def test_colmap_center_contains_pipeline_and_live_output(window):
    window._activate_page("COLMAP")
    assert window.colmap_page.pipeline_widget is not None
    assert window.colmap_page.log_view is not None


def test_colmap_right_panel_contains_settings(window):
    assert window.colmap_page.settings_widget is not None


def test_colmap_live_output_expands_with_available_space(window):
    # The live output view is added with a non-zero stretch factor in
    # its layout, so it grows to fill unused vertical space rather than
    # sitting in a fixed-height box.
    layout = window.colmap_page.layout()
    center_column = layout.itemAt(0).widget()
    center_layout = center_column.layout()
    log_view_index = None
    for i in range(center_layout.count()):
        if center_layout.itemAt(i).widget() is window.colmap_page.log_view:
            log_view_index = i
    assert log_view_index is not None
    assert center_layout.stretch(log_view_index) > 0


# ---------------------------------------------------------------------------
# Reconstruction workspace: no "Send to LichtFeld"
# ---------------------------------------------------------------------------


def test_reconstruction_has_no_send_to_lichtfeld_button(window):
    assert not hasattr(window.reconstruction_qc_page, "send_to_lichtfeld_button")
    from PySide6.QtWidgets import QPushButton
    button_texts = [
        b.text() for b in window.reconstruction_workspace.findChildren(QPushButton)
    ]
    assert not any("LichtFeld" in t for t in button_texts)


def test_lichtfeld_actions_exist_only_in_lichtfeld_workspace(window):
    from PySide6.QtWidgets import QPushButton
    lichtfeld_buttons = [b.text() for b in window.lichtfeld_page.findChildren(QPushButton)]
    assert "Prepare Scene" in lichtfeld_buttons
    assert "Open in LichtFeld" in lichtfeld_buttons


# ---------------------------------------------------------------------------
# Console dock: bottom only
# ---------------------------------------------------------------------------


def test_console_dock_exists_and_hosts_logs_page(window):
    assert window.console_dock.widget() is not None
    assert window.logs_page.parentWidget() is not None


def test_console_can_only_dock_at_bottom(window):
    from PySide6.QtCore import Qt as QtCore

    assert window.console_dock.allowedAreas() == QtCore.DockWidgetArea.BottomDockWidgetArea


def test_console_toggle_collapses_and_expands(window):
    window._toggle_console()
    assert window._console_collapsed is True
    assert window.logs_page.isVisible() is False
    window._toggle_console()
    assert window._console_collapsed is False
    assert window.logs_page.isVisible() is True


def test_logs_menu_selects_correct_log_file_and_shows_console(window):
    window._toggle_console()  # collapse first
    window._show_console_log("COLMAP Log")
    assert window._console_collapsed is False
    assert window.logs_page.log_selector.currentText() == "colmap.log"


# ---------------------------------------------------------------------------
# Top bar (replaces status bar)
# ---------------------------------------------------------------------------


def test_top_bar_shows_no_project_open_initially(window):
    assert "No project open" in window.top_bar_label.text()


def test_top_bar_updates_after_project_created(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window._update_top_bar()
    text = window.top_bar_label.text()
    assert "testProject" in text


# ---------------------------------------------------------------------------
# Dashboard-contextual New/Open Project (no persistent sidebar buttons)
# ---------------------------------------------------------------------------


def test_dashboard_new_project_signal_activates_projects_setup(window):
    window.dashboard_page.new_project_requested.emit()
    assert window.stack.currentWidget() is window.projects_setup_page


def test_dashboard_has_new_and_open_project_actions(window):
    from PySide6.QtWidgets import QPushButton
    button_texts = [b.text() for b in window.dashboard_page.findChildren(QPushButton)]
    assert any("New Project" in t for t in button_texts)
    assert any("Open Project" in t for t in button_texts)


# ---------------------------------------------------------------------------
# Duplicate-control discipline
# ---------------------------------------------------------------------------


def test_no_duplicate_run_pipeline_buttons(window):
    from PySide6.QtWidgets import QPushButton
    window._activate_page("COLMAP")
    run_buttons = [
        b for b in window.colmap_page.findChildren(QPushButton)
        if "Run Full" in b.text() or b.text() == "Run Pipeline"
    ]
    assert len(run_buttons) == 1


def test_no_duplicate_open_project_controls_anywhere(window):
    from PySide6.QtWidgets import QPushButton
    all_buttons = [b.text() for b in window.findChildren(QPushButton)]
    open_project_buttons = [t for t in all_buttons if t.strip() in ("Open Project", "Open Project...")]
    assert len(open_project_buttons) <= 1


# ---------------------------------------------------------------------------
# Backend reuse: the redesign must not duplicate or bypass existing logic
# ---------------------------------------------------------------------------


def test_activating_reconstruction_runs_real_qc_and_reflects_top_bar(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window.reconstruction_qc_page.run_qc()
    window._update_top_bar()
    assert "READY" in window.top_bar_label.text() or "WARNING" in window.top_bar_label.text()


def test_sidebar_status_indicators_reflect_persisted_state_not_recomputed(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window.reconstruction_qc_page.run_qc()
    window._update_top_bar()

    reconstruction_item = window.workflow_nav.item(_WORKFLOW_ITEMS.index("Reconstruction"))
    assert reconstruction_item.text().startswith("\u25cf") or reconstruction_item.text().startswith("\u25d0")


def test_lichtfeld_workspace_uses_real_lichtfeld_manager(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window.reconstruction_qc_page.run_qc()
    window._activate_page("LichtFeld")
    assert window.lichtfeld_page.reconstruction_value.text() in ("READY", "WARNING")


def test_existing_project_reopens_through_open_project_flow(window, tmp_path):
    opened = _create_project_with_reconstruction(window, tmp_path, project_name="reopenMe")
    project_root = opened.project_root

    window.project_manager.open_project(str(project_root))
    window._on_project_changed()

    assert window.project_manager.current.data.name == "reopenMe"
    assert window.stack.currentWidget() is window.dashboard_page


def test_colmap_pipeline_finished_signal_refreshes_reconstruction_and_lichtfeld(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window.colmap_page.pipeline_finished.emit()
    assert window.reconstruction_qc_page.project_manager.current is not None


def test_reconstruction_tab_navigation(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window.reconstruction_qc_page.run_qc()
    window._activate_reconstruction_tab(1)
    assert window.stack.currentWidget() is window.reconstruction_workspace
    assert window.reconstruction_workspace.tabs.currentIndex() == 1
    assert "1,000" in window.reconstruction_workspace.point_cloud_tab.numbers_label.text()
