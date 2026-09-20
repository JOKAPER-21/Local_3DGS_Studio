from pathlib import Path

from src.core.config_manager import AppSettings, ConfigManager, ExternalSoftwarePaths


def test_save_and_load_last_project(tmp_path: Path):
    config_dir = tmp_path / "config"
    manager = ConfigManager(config_dir)
    project_root = tmp_path / "myProject"

    manager.save_last_project(project_root)
    loaded = manager.load_last_project()

    assert loaded == project_root
    # Must never write last_project.json inside the project folder itself.
    assert not (project_root / "last_project.json").exists()


def test_load_last_project_returns_none_when_absent(tmp_path: Path):
    manager = ConfigManager(tmp_path / "config")
    assert manager.load_last_project() is None


def test_clear_last_project(tmp_path: Path):
    manager = ConfigManager(tmp_path / "config")
    manager.save_last_project(tmp_path / "someProject")
    manager.clear_last_project()
    assert manager.load_last_project() is None


def test_settings_roundtrip(tmp_path: Path):
    manager = ConfigManager(tmp_path / "config")
    settings = AppSettings(
        default_project_root=str(tmp_path),
        external_software=ExternalSoftwarePaths(colmap="C:/colmap.bat"),
    )
    manager.save_settings(settings)

    loaded = manager.load_settings()
    assert loaded.default_project_root == str(tmp_path)
    assert loaded.external_software.colmap == "C:/colmap.bat"


def test_settings_defaults_when_missing(tmp_path: Path):
    manager = ConfigManager(tmp_path / "config")
    settings = manager.load_settings()
    assert settings.default_project_root == ""
    assert settings.external_software.colmap == ""
