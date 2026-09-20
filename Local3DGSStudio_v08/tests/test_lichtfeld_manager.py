import stat
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from src.core.config_manager import ConfigManager
from src.core.lichtfeld_config import LichtFeldConfig
from src.core.lichtfeld_manager import LichtFeldManager
from src.core.lichtfeld_staging import cleanup_staging
from src.core.project_manager import ProjectManager
from src.core.reconstruction_qc import QC_STATE_FAILED, QC_STATE_NOT_READY, QC_STATE_READY, QCResult


@pytest.fixture(scope="module")
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


def _open_project(tmp_path: Path) -> ProjectManager:
    config = ConfigManager(tmp_path / "appConfig")
    manager = ProjectManager(config)
    manager.create_project(str(tmp_path / "projects"), "gsOfficeBuildingPillar", "v01")
    return manager


def _write_fake_images(directory: Path, count: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (directory / f"img_{i:03d}.jpg").write_bytes(b"fake jpg bytes")


def _write_fake_sparse_model(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "cameras.bin").write_bytes(b"fake cameras bin")
    (directory / "images.bin").write_bytes(b"fake images bin")
    (directory / "points3D.bin").write_bytes(b"fake points3D bin")


def _ready_qc_result() -> QCResult:
    return QCResult(
        total_images=293, registered_images=293, registration_percentage=100.0,
        cameras=293, registered_cameras=293, frames=293, registered_frames=293,
        points=139741, observations=1731278,
        mean_track_length=12.389191, mean_observations_per_image=5908.798635,
        mean_reprojection_error_px=0.937114,
        camera_models=["SIMPLE_RADIAL"], distorted_camera_models=["SIMPLE_RADIAL"],
        required_files_present=True, database_valid=True, image_source_valid=True,
        metrics_parsed=True, state=QC_STATE_READY,
    )


@pytest.fixture()
def fake_lichtfeld_executable(tmp_path):
    script = tmp_path / "fake_lichtfeld.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_validate_executable_missing_path(tmp_path):
    manager = LichtFeldManager(_open_project(tmp_path), LichtFeldConfig(executable_path=""))
    ok, message = manager.validate_executable()
    assert ok is False
    assert "not configured" in message.lower()


def test_validate_executable_nonexistent_file(tmp_path):
    manager = LichtFeldManager(
        _open_project(tmp_path), LichtFeldConfig(executable_path=str(tmp_path / "nope.exe"))
    )
    ok, message = manager.validate_executable()
    assert ok is False
    assert "not found" in message.lower()


def test_validate_executable_found(tmp_path, fake_lichtfeld_executable):
    manager = LichtFeldManager(
        _open_project(tmp_path), LichtFeldConfig(executable_path=str(fake_lichtfeld_executable))
    )
    ok, path = manager.validate_executable()
    assert ok is True
    assert path == str(fake_lichtfeld_executable)


def test_send_to_lichtfeld_blocked_when_qc_not_ready(tmp_path, fake_lichtfeld_executable):
    project_manager = _open_project(tmp_path)
    config = LichtFeldConfig(executable_path=str(fake_lichtfeld_executable))
    manager = LichtFeldManager(project_manager, config)

    not_ready = QCResult(state=QC_STATE_NOT_READY)
    result = manager.send_to_lichtfeld(not_ready)

    assert result.success is False
    assert "not eligible" in result.error.lower() or "not ready" in result.error.lower()


def test_send_to_lichtfeld_blocked_when_qc_failed(tmp_path, fake_lichtfeld_executable):
    project_manager = _open_project(tmp_path)
    config = LichtFeldConfig(executable_path=str(fake_lichtfeld_executable))
    manager = LichtFeldManager(project_manager, config)

    failed = QCResult(state=QC_STATE_FAILED)
    result = manager.send_to_lichtfeld(failed)

    assert result.success is False


def test_send_to_lichtfeld_fails_when_executable_missing(tmp_path):
    project_manager = _open_project(tmp_path)
    resolver = project_manager.current.resolver
    _write_fake_images(resolver.images, 3)
    _write_fake_sparse_model(resolver.colmap / "sparse" / "0")

    config = LichtFeldConfig(executable_path="")
    manager = LichtFeldManager(project_manager, config)

    result = manager.send_to_lichtfeld(_ready_qc_result())

    assert result.success is False
    assert "not configured" in result.error.lower()
    assert result.staging is None  # never got as far as staging


def test_send_to_lichtfeld_fails_when_sparse_model_incomplete(tmp_path, fake_lichtfeld_executable):
    project_manager = _open_project(tmp_path)
    resolver = project_manager.current.resolver
    _write_fake_images(resolver.images, 3)
    (resolver.colmap / "sparse" / "0").mkdir(parents=True, exist_ok=True)
    # Deliberately incomplete: only one of the three required files.
    (resolver.colmap / "sparse" / "0" / "cameras.bin").write_bytes(b"only this one")

    config = LichtFeldConfig(executable_path=str(fake_lichtfeld_executable))
    manager = LichtFeldManager(project_manager, config)

    try:
        result = manager.send_to_lichtfeld(_ready_qc_result())
        assert result.success is False
        assert result.staging is not None
        assert not result.staging.sparse_files_present
    finally:
        cleanup_staging(project_manager.current.data.name, project_manager.current.data.version)


def test_send_to_lichtfeld_full_success(qt_app, tmp_path, fake_lichtfeld_executable):
    project_manager = _open_project(tmp_path)
    resolver = project_manager.current.resolver
    _write_fake_images(resolver.images, 5)
    _write_fake_sparse_model(resolver.colmap / "sparse" / "0")

    config = LichtFeldConfig(executable_path=str(fake_lichtfeld_executable))
    manager = LichtFeldManager(project_manager, config)

    try:
        result = manager.send_to_lichtfeld(_ready_qc_result())

        assert result.success is True
        assert result.pid > 0
        assert result.executable_path == str(fake_lichtfeld_executable)
        assert result.staging is not None and result.staging.ok
        # Source data must be completely untouched.
        assert len(list(resolver.images.iterdir())) == 5
        assert (resolver.colmap / "sparse" / "0" / "cameras.bin").read_bytes() == b"fake cameras bin"
    finally:
        cleanup_staging(project_manager.current.data.name, project_manager.current.data.version)


def test_send_to_lichtfeld_never_creates_permanent_colmap_images_folder(qt_app, tmp_path, fake_lichtfeld_executable):
    project_manager = _open_project(tmp_path)
    resolver = project_manager.current.resolver
    _write_fake_images(resolver.images, 3)
    _write_fake_sparse_model(resolver.colmap / "sparse" / "0")

    config = LichtFeldConfig(executable_path=str(fake_lichtfeld_executable))
    manager = LichtFeldManager(project_manager, config)

    try:
        manager.send_to_lichtfeld(_ready_qc_result())
        assert not (resolver.colmap / "images").exists()
    finally:
        cleanup_staging(project_manager.current.data.name, project_manager.current.data.version)
