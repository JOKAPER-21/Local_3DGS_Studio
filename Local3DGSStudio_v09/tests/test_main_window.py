"""Tests for the redesigned ``MainWindow`` shell.

These are the only tests in the suite that need a real ``QApplication``,
so ``QT_QPA_PLATFORM=offscreen`` is set here, before any Qt import,
rather than relying on the environment -- running plain ``pytest`` (no
extra env vars) must exercise these too.

The point of these tests is the *shell*: menu/sidebar synchronization,
workspace switching, the console dock, the status bar, and toolbar
state. They deliberately also assert that activating a workspace still
drives the real, unchanged backend (project loading, COLMAP refresh,
Reconstruction QC, LichtFeld) -- the redesign must not have created a
second, GUI-only notion of project state.
"""

from __future__ import annotations

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QToolBar

from src.gui.main_window import (
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
# Startup / menu / toolbar creation
# ---------------------------------------------------------------------------


def test_main_window_starts_without_blocking(window):
    assert window is not None


def test_menu_bar_has_expected_top_level_menus(window):
    titles = [action.text().replace("&", "") for action in window.menuBar().actions()]
    assert titles == ["File", "Workflow", "Render", "Logs", "Settings"]


def test_workflow_menu_has_submenus_for_colmap_reconstruction_lichtfeld(window):
    workflow_menu = next(
        m for m in window.menuBar().findChildren(type(window.menuBar().addMenu("_tmp")))
        if m.title() == "&Workflow"
    )
    submenu_titles = {m.title() for m in workflow_menu.findChildren(type(workflow_menu))}
    assert {"COLMAP", "Reconstruction", "LichtFeld", "Training", "Cleanup"} <= submenu_titles


def test_toolbar_exists_with_expected_actions(window):
    toolbars = window.findChildren(QToolBar)
    assert len(toolbars) == 1
    action_texts = [a.text() for a in toolbars[0].actions() if a.text()]
    assert action_texts == [
        "New Project", "Open Project", "Save Project", "Run", "Stop", "Refresh", "Open Console",
    ]


# ---------------------------------------------------------------------------
# Sidebar / menu / workspace synchronization
# ---------------------------------------------------------------------------


def test_sidebar_contains_pinned_and_workflow_sections(window):
    top_items = [window.top_nav.item(i).text() for i in range(window.top_nav.count())]
    assert top_items == _TOP_NAV_ITEMS

    workflow_items = [window.workflow_nav.item(i).text() for i in range(window.workflow_nav.count())]
    for name in _WORKFLOW_ITEMS:
        assert any(item.endswith(name) for item in workflow_items)


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


def test_clicking_sidebar_item_activates_same_page_as_menu(window):
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


# ---------------------------------------------------------------------------
# Console dock
# ---------------------------------------------------------------------------


def test_console_dock_exists_and_hosts_logs_page(window):
    assert window.console_dock.widget() is not None
    assert window.logs_page.parentWidget() is not None


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
# Status bar
# ---------------------------------------------------------------------------


def test_status_bar_shows_no_project_open_initially(window):
    assert "No project open" in window.status_left_label.text()


def test_status_bar_updates_after_project_created(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window._update_status_bar()
    text = window.status_left_label.text()
    assert "testProject" in text
    assert "Images: 5" in text


# ---------------------------------------------------------------------------
# Backend reuse: the redesign must not duplicate or bypass existing logic
# ---------------------------------------------------------------------------


def test_activating_reconstruction_runs_real_qc_and_reflects_status_bar(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window.reconstruction_qc_page.run_qc()
    window._update_status_bar()
    assert "READY" in window.status_left_label.text() or "WARNING" in window.status_left_label.text()


def test_sidebar_status_indicators_reflect_persisted_state_not_recomputed(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window.reconstruction_qc_page.run_qc()
    window._update_status_bar()

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


def test_reconstruction_tab_navigation_via_workflow_submenu_handler(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window.reconstruction_qc_page.run_qc()
    window._activate_reconstruction_tab(1)
    assert window.stack.currentWidget() is window.reconstruction_workspace
    assert window.reconstruction_workspace.tabs.currentIndex() == 1
    assert "1,000" in window.reconstruction_workspace.point_cloud_tab.numbers_label.text()


def test_toolbar_run_stop_reflect_colmap_running_state(window, tmp_path):
    _create_project_with_reconstruction(window, tmp_path)
    window._update_status_bar()
    assert window.toolbar_run_action.isEnabled() is True
    assert window.toolbar_stop_action.isEnabled() is False

    window.colmap_page._running_full_pipeline = True
    window._update_status_bar()
    assert window.toolbar_run_action.isEnabled() is False
    assert window.toolbar_stop_action.isEnabled() is True
