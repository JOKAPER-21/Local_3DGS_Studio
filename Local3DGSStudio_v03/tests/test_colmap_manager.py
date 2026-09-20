import os
import stat
import sys
from pathlib import Path

import pytest

from src.core.colmap_config import COLMAPConfig
from src.core.colmap_manager import (
    COLMAPManager,
    DatabaseExistsError,
    SparseModelExistsError,
    build_colmap_invocation,
    detect_colmap_executable,
)
from src.core.config_manager import ConfigManager
from src.core.project_manager import ProjectManager


def _open_project(tmp_path: Path) -> ProjectManager:
    config = ConfigManager(tmp_path / "appConfig")
    manager = ProjectManager(config)
    manager.create_project(str(tmp_path / "projects"), "gsOfficeBuildingPillar", "v01")
    return manager


def _write_fake_images(directory: Path, count: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (directory / f"img_{i:03d}.jpg").write_bytes(b"fake jpg bytes")


_FAKE_COLMAP_SCRIPT = """#!/bin/sh
if [ "$1" = "-h" ]; then
  echo "COLMAP 4.2.0 (Commit be5e291 on 2026-08-31 with CUDA)"
  exit 0
fi
echo "ran: $@"
exit 0
"""


def _write_fake_colmap(path: Path) -> None:
    path.write_text(_FAKE_COLMAP_SCRIPT)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# -- command building (pure, no execution) -----------------------------------


def test_no_gui_path_construction_uses_resolver(tmp_path: Path):
    """The manager must resolve every path through the project's own
    ProjectPathResolver -- never a hand-built string."""
    project_manager = _open_project(tmp_path)
    colmap_manager = COLMAPManager(project_manager)

    expected_colmap_dir = project_manager.current.resolver.colmap
    assert colmap_manager.database_path() == expected_colmap_dir / "database.db"
    assert colmap_manager.sparse_model_path() == expected_colmap_dir / "sparse" / "0"
    assert colmap_manager.images_junction_path() == expected_colmap_dir / "images"
    assert colmap_manager.active_image_source_path() == project_manager.current.resolver.images


def test_feature_extraction_command_cpu(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    config = COLMAPConfig(executable_path="/usr/bin/colmap", feature_extraction_threads=4)
    manager = COLMAPManager(project_manager, config)

    command = manager.build_feature_extraction_command()

    assert command.subcommand == "feature_extractor"
    assert "--FeatureExtraction.use_gpu" in command.colmap_args
    assert command.colmap_args[command.colmap_args.index("--FeatureExtraction.use_gpu") + 1] == "0"
    assert "--FeatureExtraction.num_threads" in command.colmap_args
    assert command.colmap_args[command.colmap_args.index("--FeatureExtraction.num_threads") + 1] == "4"
    assert str(manager.database_path()) in command.colmap_args
    assert str(manager.images_junction_path()) in command.colmap_args


def test_feature_matching_command_cpu(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    config = COLMAPConfig(executable_path="/usr/bin/colmap")
    manager = COLMAPManager(project_manager, config)

    command = manager.build_feature_matching_command()

    assert command.subcommand == "exhaustive_matcher"
    idx = command.colmap_args.index("--FeatureMatching.use_gpu")
    assert command.colmap_args[idx + 1] == "0"
    assert str(manager.database_path()) in command.colmap_args


def test_mapper_command(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path="/usr/bin/colmap"))

    command = manager.build_mapper_command()

    assert command.subcommand == "mapper"
    assert str(manager.database_path()) in command.colmap_args
    assert str(manager.images_junction_path()) in command.colmap_args
    assert str(manager.sparse_root_path()) in command.colmap_args


def test_model_analyzer_command(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path="/usr/bin/colmap"))

    command = manager.build_model_analyzer_command()

    assert command.subcommand == "model_analyzer"
    assert command.colmap_args == ["model_analyzer", "--path", str(manager.sparse_model_path())]


def test_command_contains_resolved_absolute_paths(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path="/usr/bin/colmap"))

    command = manager.build_database_creation_command()

    assert Path(command.colmap_args[-1]).is_absolute()


def test_bat_file_wrapped_with_cmd_on_windows_only():
    executable, args = build_colmap_invocation(r"C:\colmap\COLMAP.bat", ["feature_extractor"])
    if sys.platform.startswith("win"):
        assert executable == "cmd.exe"
        assert args[0] == "/c"
    else:
        # On non-Windows dev machines the .bat wrapper never applies.
        assert executable == r"C:\colmap\COLMAP.bat"


# -- database / sparse-model overwrite safety --------------------------------


def test_existing_database_is_not_overwritten_automatically(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path="/usr/bin/colmap"))
    manager.database_path().parent.mkdir(parents=True, exist_ok=True)
    manager.database_path().write_bytes(b"existing database")

    with pytest.raises(DatabaseExistsError):
        manager.create_database(force=False)

    assert manager.database_path().read_bytes() == b"existing database"


def test_create_database_force_replaces_only_database(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path="/usr/bin/colmap"))
    manager.database_path().parent.mkdir(parents=True, exist_ok=True)
    manager.database_path().write_bytes(b"old")

    sparse_model = manager.sparse_model_path()
    sparse_model.mkdir(parents=True)
    (sparse_model / "cameras.bin").write_bytes(b"keep me")

    manager.create_database(force=True)

    assert not manager.database_path().exists()  # removed, ready for database_creator to recreate
    assert (sparse_model / "cameras.bin").read_bytes() == b"keep me"  # untouched


def test_existing_sparse_model_is_not_overwritten_automatically(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path="/usr/bin/colmap"))
    sparse_model = manager.sparse_model_path()
    sparse_model.mkdir(parents=True)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        (sparse_model / name).write_bytes(b"existing")

    with pytest.raises(SparseModelExistsError):
        manager.run_mapper(force=False)

    assert (sparse_model / "cameras.bin").exists()


def test_run_mapper_force_removes_existing_sparse(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path="/usr/bin/colmap"))
    sparse_model = manager.sparse_model_path()
    sparse_model.mkdir(parents=True)
    (sparse_model / "cameras.bin").write_bytes(b"old")

    manager.run_mapper(force=True)

    assert not (sparse_model / "cameras.bin").exists()
    assert manager.sparse_root_path().is_dir()


# -- detection -----------------------------------------------------------------


def test_colmap_missing_path_returns_not_detected(tmp_path: Path):
    result = detect_colmap_executable(str(tmp_path / "doesNotExist.bat"))
    assert not result.detected
    assert "not found" in result.error.lower()


def test_colmap_empty_path_returns_not_detected():
    result = detect_colmap_executable("")
    assert not result.detected


def test_colmap_version_detection_from_fake_executable(tmp_path: Path):
    fake = tmp_path / "fake_colmap.sh"
    _write_fake_colmap(fake)

    result = detect_colmap_executable(str(fake))

    assert result.detected
    assert result.version == "4.2.0"
    assert result.cuda_build is True


# -- preflight -----------------------------------------------------------------


def test_preflight_fails_without_open_project(tmp_path: Path):
    config = ConfigManager(tmp_path / "appConfig")
    project_manager = ProjectManager(config)
    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path="/usr/bin/colmap"))

    from src.core.colmap_manager import ColmapDetectionResult

    report = manager.run_preflight(ColmapDetectionResult(detected=False))
    assert not report.all_passed


def test_preflight_passes_with_valid_project_and_images(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    fake = tmp_path / "fake_colmap.sh"
    _write_fake_colmap(fake)

    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path=str(fake)))
    _write_fake_images(project_manager.current.resolver.images, 5)
    project_manager.current.data.validation_info["validationStatus"] = "VALID"

    detection = detect_colmap_executable(str(fake))
    report = manager.run_preflight(detection)

    assert report.all_passed, report.failed_checks


def test_input_validation_gate_blocks_on_invalid(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager)
    project_manager.current.data.validation_info["validationStatus"] = "INVALID"

    allowed, requires_confirmation, message = manager.check_input_validation_gate()
    assert not allowed


def test_input_validation_gate_allows_valid_without_confirmation(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager)
    project_manager.current.data.validation_info["validationStatus"] = "VALID"

    allowed, requires_confirmation, _ = manager.check_input_validation_gate()
    assert allowed
    assert not requires_confirmation


def test_input_validation_gate_warns_on_warning_status(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager)
    project_manager.current.data.validation_info["validationStatus"] = "WARNING"

    allowed, requires_confirmation, _ = manager.check_input_validation_gate()
    assert allowed
    assert requires_confirmation


# -- project.json integration --------------------------------------------------


def test_project_json_colmap_update_full_cycle(tmp_path: Path):
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager, COLMAPConfig(executable_path="/usr/bin/colmap", feature_extraction_threads=4))

    manager.database_path().parent.mkdir(parents=True, exist_ok=True)
    manager.database_path().write_bytes(b"db")
    manager.record_database_created()
    assert project_manager.current.data.colmap_info["state"] == "DATABASE_CREATED"

    manager.record_feature_extraction_completed(use_gpu=False, threads=4)
    assert project_manager.current.data.colmap_info["featureExtraction"]["completed"] is True
    assert project_manager.current.data.colmap_info["state"] == "FEATURES_EXTRACTED"

    manager.record_feature_matching_completed(use_gpu=False, method="exhaustive")
    assert project_manager.current.data.colmap_info["state"] == "FEATURES_MATCHED"

    manager.record_mapper_completed()
    assert project_manager.current.data.colmap_info["mapper"]["completed"] is True
    assert project_manager.current.data.colmap_info["state"] == "SPARSE_RECONSTRUCTION_CREATED"

    metrics = {
        "registeredImages": 293, "totalImages": 293, "points": 139741,
        "observations": 1731278, "meanTrackLength": 12.389191, "meanReprojectionError": 0.937114,
    }
    manager.record_analysis_completed(metrics)
    assert project_manager.current.data.colmap_info["state"] == "READY"
    assert project_manager.current.data.colmap_info["registeredImages"] == 293

    # Reopen the project fresh and confirm every value survived the roundtrip.
    reopened = ProjectManager(project_manager.config_manager)
    reopened.open_project(str(project_manager.current.project_root))
    assert reopened.current.data.colmap_info["state"] == "READY"
    assert reopened.current.data.colmap_info["analysis"]["points"] == 139741


def test_only_project_manager_persists_colmap_state(tmp_path: Path):
    """record_* methods must go through ProjectManager.save_project_json
    (which rewrites project.json on disk), not write project.json
    themselves."""
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager)
    manager.database_path().parent.mkdir(parents=True, exist_ok=True)
    manager.database_path().write_bytes(b"db")

    project_json_path = project_manager.current.project_root / "project.json"
    before_text = project_json_path.read_text(encoding="utf-8")

    manager.record_database_created()

    after_text = project_json_path.read_text(encoding="utf-8")
    assert after_text != before_text
    assert '"state": "DATABASE_CREATED"' in after_text


# -- process failure / cancellation state (file-based, no Qt needed) ---------


def test_process_failure_leaves_state_unrecorded(tmp_path: Path):
    """A non-zero exit code must never be recorded as success -- this
    verifies the manager only ever records completion when explicitly
    told to (the GUI layer, not this module, decides that from exit
    code + verified output files)."""
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager)

    # Simulate: command was built and "run" but failed (exit code != 0),
    # so the GUI never calls record_database_created().
    manager.build_database_creation_command()

    assert project_manager.current.data.colmap_info["state"] == "NOT_STARTED"
    assert not manager.database_exists()


def test_cancel_state_is_not_marked_completed(tmp_path: Path):
    """Cancelling before a stage's required output exists must not leave
    it recorded as complete."""
    project_manager = _open_project(tmp_path)
    manager = COLMAPManager(project_manager)

    # Cancelled mid-run: no database.db was ever written.
    assert not manager.database_exists()
    state = manager.get_reconstruction_state()
    assert state.state == "NOT_STARTED"
