from pathlib import Path

import pytest

from src.core.project_json import (
    ProjectData,
    ProjectJsonError,
    read_project_json,
    write_project_json,
)


def test_write_then_read_roundtrip(tmp_path: Path):
    data = ProjectData(name="gsOfficeBuildingPillar", version="v01")
    write_project_json(tmp_path, data)

    loaded = read_project_json(tmp_path)

    assert loaded.name == "gsOfficeBuildingPillar"
    assert loaded.version == "v01"


def test_all_internal_paths_are_relative_not_absolute(tmp_path: Path):
    data = ProjectData(name="gsOfficeBuildingPillar", version="v01")
    write_project_json(tmp_path, data)

    loaded = read_project_json(tmp_path)
    paths_dict = loaded.relative_paths.to_dict()

    for value in paths_dict.values():
        assert not Path(value).is_absolute()
        assert str(tmp_path) not in value


def test_read_missing_project_json_raises(tmp_path: Path):
    with pytest.raises(ProjectJsonError):
        read_project_json(tmp_path)


def test_read_malformed_project_json_raises(tmp_path: Path):
    (tmp_path / "project.json").write_text("{ not valid json")
    with pytest.raises(ProjectJsonError):
        read_project_json(tmp_path)


def test_read_project_json_missing_required_fields_raises(tmp_path: Path):
    (tmp_path / "project.json").write_text('{"application": {}}')
    with pytest.raises(ProjectJsonError):
        read_project_json(tmp_path)
