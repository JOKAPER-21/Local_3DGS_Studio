from pathlib import Path

import pytest

from src.core.project_paths import RelativeProjectPaths
from src.core.project_structure import ProjectAlreadyExistsError, ProjectStructureManager


def test_create_project_creates_all_directories(tmp_path: Path):
    manager = ProjectStructureManager()
    relative = RelativeProjectPaths.for_version("v01")
    project_root = tmp_path / "gsOfficeBuildingPillar"

    report = manager.create_project(project_root, relative)

    assert (project_root / "rawData" / "images" / "v01").is_dir()
    assert (project_root / "rawData" / "videos").is_dir()
    assert (project_root / "colmap" / "v01").is_dir()
    assert (project_root / "lichtFeld" / "v01").is_dir()
    assert (project_root / "export" / "pointCloud").is_dir()
    assert (project_root / "export" / "splats").is_dir()
    assert (project_root / "renders").is_dir()
    assert (project_root / "logs").is_dir()
    assert len(report.missing_directories) == 0
    # Architecture rule: no persistent colmap/vNN/images junction folder.
    assert not (project_root / "colmap" / "v01" / "images").exists()


def test_create_project_raises_if_project_already_exists(tmp_path: Path):
    manager = ProjectStructureManager()
    relative = RelativeProjectPaths.for_version("v01")
    project_root = tmp_path / "gsOfficeBuildingPillar"

    manager.create_project(project_root, relative)

    with pytest.raises(ProjectAlreadyExistsError):
        manager.create_project(project_root, relative)


def test_create_project_raises_if_folder_has_unrelated_files(tmp_path: Path):
    manager = ProjectStructureManager()
    relative = RelativeProjectPaths.for_version("v01")
    project_root = tmp_path / "existingStuff"
    project_root.mkdir()
    (project_root / "note.txt").write_text("not a project")

    with pytest.raises(ProjectAlreadyExistsError):
        manager.create_project(project_root, relative)


def test_validate_project_reports_missing_directories(tmp_path: Path):
    manager = ProjectStructureManager()
    relative = RelativeProjectPaths.for_version("v01")
    project_root = tmp_path / "incompleteProject"
    project_root.mkdir()
    (project_root / "rawData").mkdir()

    report = manager.validate_project(project_root, relative)

    assert not report.is_valid
    assert any("images" in str(p) for p in report.missing_directories)


def test_repair_project_creates_only_missing_directories(tmp_path: Path):
    manager = ProjectStructureManager()
    relative = RelativeProjectPaths.for_version("v01")
    project_root = tmp_path / "repairMe"
    manager.create_project(project_root, relative)

    # Simulate a user accidentally deleting one folder.
    import shutil

    shutil.rmtree(project_root / "renders")
    assert not (project_root / "renders").exists()

    report = manager.repair_project(project_root, relative)

    assert (project_root / "renders").is_dir()
    assert any("renders" in str(p) for p in report.created_directories)


def test_create_version_does_not_touch_previous_version(tmp_path: Path):
    manager = ProjectStructureManager()
    project_root = tmp_path / "versionedProject"
    relative_v1 = RelativeProjectPaths.for_version("v01")
    manager.create_project(project_root, relative_v1)

    marker = project_root / "rawData" / "images" / "v01" / "photo001.jpg"
    marker.write_bytes(b"fake image data")

    images_v2, colmap_v2, lichtfeld_v2 = manager.create_version(project_root, "v02")

    assert images_v2.is_dir()
    assert colmap_v2.is_dir()
    assert lichtfeld_v2.is_dir()
    assert marker.exists()  # v01 data untouched
    assert marker.read_bytes() == b"fake image data"
