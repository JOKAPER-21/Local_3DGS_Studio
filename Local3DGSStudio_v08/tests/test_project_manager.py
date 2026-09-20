from pathlib import Path

import pytest

from src.core.config_manager import ConfigManager
from src.core.project_manager import ProjectLoadError, ProjectManager
from src.core.project_structure import ProjectAlreadyExistsError
from src.utils.validators import ValidationError


def _manager(tmp_path: Path) -> ProjectManager:
    config = ConfigManager(tmp_path / "appConfig")
    return ProjectManager(config)


def test_create_project_end_to_end(tmp_path: Path):
    manager = _manager(tmp_path)
    project_root = tmp_path / "projects"

    opened = manager.create_project(str(project_root), "gsOfficeBuildingPillar", "v01")

    assert opened.project_root == project_root / "gsOfficeBuildingPillar"
    assert (opened.project_root / "project.json").exists()
    assert opened.resolver.images.is_dir()
    assert manager.current is opened


def test_create_project_invalid_name_raises(tmp_path: Path):
    manager = _manager(tmp_path)
    with pytest.raises(ValidationError):
        manager.create_project(str(tmp_path / "projects"), "Not Valid", "v01")


def test_create_project_twice_raises(tmp_path: Path):
    manager = _manager(tmp_path)
    project_root = tmp_path / "projects"
    manager.create_project(str(project_root), "gsOfficeBuildingPillar", "v01")

    with pytest.raises(ProjectAlreadyExistsError):
        manager.create_project(str(project_root), "gsOfficeBuildingPillar", "v01")


def test_open_project_loads_existing_project(tmp_path: Path):
    manager = _manager(tmp_path)
    project_root = tmp_path / "projects"
    created = manager.create_project(str(project_root), "gsOfficeBuildingPillar", "v01")

    manager2 = _manager(tmp_path)
    opened = manager2.open_project(str(created.project_root))

    assert opened.data.name == "gsOfficeBuildingPillar"


def test_open_missing_project_raises(tmp_path: Path):
    manager = _manager(tmp_path)
    with pytest.raises(ProjectLoadError):
        manager.open_project(str(tmp_path / "doesNotExist"))


def test_create_project_remembers_last_opened(tmp_path: Path):
    manager = _manager(tmp_path)
    project_root = tmp_path / "projects"
    created = manager.create_project(str(project_root), "gsOfficeBuildingPillar", "v01")

    remembered = manager.config_manager.load_last_project()
    assert remembered == created.project_root


def test_load_last_opened_project_success(tmp_path: Path):
    manager = _manager(tmp_path)
    project_root = tmp_path / "projects"
    created = manager.create_project(str(project_root), "gsOfficeBuildingPillar", "v01")

    fresh_manager = ProjectManager(manager.config_manager)
    fresh_manager.current = None
    loaded = fresh_manager.load_last_opened_project()

    assert loaded is not None
    assert loaded.project_root == created.project_root


def test_load_last_opened_project_missing_returns_none(tmp_path: Path):
    manager = _manager(tmp_path)
    manager.config_manager.save_last_project(tmp_path / "gone")

    result = manager.load_last_opened_project()
    assert result is None


def test_load_last_opened_project_none_remembered(tmp_path: Path):
    manager = _manager(tmp_path)
    assert manager.load_last_opened_project() is None


def test_set_active_version_creates_new_version_without_deleting_old(tmp_path: Path):
    manager = _manager(tmp_path)
    project_root = tmp_path / "projects"
    manager.create_project(str(project_root), "gsOfficeBuildingPillar", "v01")

    v1_images = manager.current.resolver.images
    marker = v1_images / "photo.jpg"
    marker.write_bytes(b"data")

    manager.set_active_version("v02")

    assert manager.get_active_version() == "v02"
    assert manager.current.resolver.images.name == "v02"
    assert marker.exists()  # v01 untouched
    assert manager.current.data.relative_paths.images == "rawData/images/v02"


def test_validate_current_project_detects_missing_directory(tmp_path: Path):
    import shutil

    manager = _manager(tmp_path)
    project_root = tmp_path / "projects"
    manager.create_project(str(project_root), "gsOfficeBuildingPillar", "v01")

    shutil.rmtree(manager.current.resolver.logs)

    report = manager.validate_current_project()
    assert not report.is_valid


def test_repair_current_project_restores_missing_directory(tmp_path: Path):
    import shutil

    manager = _manager(tmp_path)
    project_root = tmp_path / "projects"
    manager.create_project(str(project_root), "gsOfficeBuildingPillar", "v01")

    shutil.rmtree(manager.current.resolver.logs)
    manager.repair_current_project()

    assert manager.current.resolver.logs.is_dir()
