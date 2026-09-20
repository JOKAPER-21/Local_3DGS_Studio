from pathlib import Path

import pytest

from src.core.config_manager import ConfigManager
from src.core.input_manager import InputManager
from src.core.project_manager import ProjectLoadError, ProjectManager


def _open_project(tmp_path: Path) -> ProjectManager:
    config = ConfigManager(tmp_path / "appConfig")
    manager = ProjectManager(config)
    manager.create_project(str(tmp_path / "projects"), "gsOfficeBuildingPillar", "v01")
    return manager


def _write_fake_images(directory: Path, count: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (directory / f"img_{i:03d}.jpg").write_bytes(b"fake jpg bytes")


def test_image_directory_resolution_matches_project_json(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)

    expected = manager.current.resolver.images
    assert input_manager.get_active_image_directory() == expected
    assert expected.name == "v01"


def test_video_directory_resolution(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)

    assert input_manager.get_video_directory() == manager.current.resolver.videos


def test_image_count_from_actual_files(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)

    _write_fake_images(input_manager.get_active_image_directory(), 5)
    assert input_manager.count_images() == 5


def test_video_count_from_actual_files(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)

    video_dir = input_manager.get_video_directory()
    video_dir.mkdir(parents=True, exist_ok=True)
    (video_dir / "clip1.mp4").write_bytes(b"fake video")
    (video_dir / "clip2.MOV").write_bytes(b"fake video")
    (video_dir / "notes.txt").write_text("ignore me")

    assert input_manager.count_videos() == 2


def test_case_insensitive_extensions_are_counted(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)
    images_dir = input_manager.get_active_image_directory()
    images_dir.mkdir(parents=True, exist_ok=True)

    for name in ("a.JPG", "b.jpeg", "c.PNG", "d.tif", "e.TIFF"):
        (images_dir / name).write_bytes(b"data")

    assert input_manager.count_images() == 5


def test_missing_image_directory_returns_empty_list(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)

    import shutil

    shutil.rmtree(input_manager.get_active_image_directory())

    assert input_manager.list_images() == []
    assert input_manager.count_images() == 0


def test_empty_image_directory_returns_empty_list(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)
    assert input_manager.list_images() == []


def test_no_project_open_raises(tmp_path: Path):
    manager = ProjectManager(ConfigManager(tmp_path / "appConfig"))
    input_manager = InputManager(manager)
    with pytest.raises(ProjectLoadError):
        input_manager.get_active_image_directory()


def test_refresh_input_data_updates_project_json(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)
    _write_fake_images(input_manager.get_active_image_directory(), 3)

    input_manager.refresh_input_data()

    assert manager.current.data.input_info["imageCount"] == 3
    reopened = manager.open_project(str(manager.current.project_root))
    assert reopened.data.input_info["imageCount"] == 3


def test_create_v02_creates_directories(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)

    new_version = input_manager.create_image_version("v02")

    assert new_version == "v02"
    assert manager.current.resolver.images.name == "v02"
    assert manager.current.resolver.images.is_dir()
    assert manager.current.resolver.colmap.is_dir()


def test_v01_preserved_after_creating_v02(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)
    v1_dir = input_manager.get_active_image_directory()
    _write_fake_images(v1_dir, 4)

    input_manager.create_image_version("v02")

    assert v1_dir.is_dir()
    assert len(list(v1_dir.glob("*.jpg"))) == 4


def test_relative_paths_after_version_creation_remain_relative(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)
    input_manager.create_image_version("v02")

    images_relative = manager.current.data.relative_paths.images
    assert not Path(images_relative).is_absolute()
    assert images_relative == "rawData/images/v02"


def test_project_json_updated_after_version_creation(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)
    input_manager.create_image_version("v02")

    reopened = manager.open_project(str(manager.current.project_root))
    assert reopened.data.version == "v02"
    assert reopened.data.input_info["activeImageVersion"] == "v02"
    assert reopened.data.colmap_info["activeVersion"] == "v02"


def test_next_version_string_scans_existing_folders(tmp_path: Path):
    manager = _open_project(tmp_path)
    input_manager = InputManager(manager)

    input_manager.create_image_version("v02")
    input_manager.create_image_version("v05")

    assert input_manager.next_version_string() == "v06"
