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


def test_reconstruction_qc_section_roundtrip(tmp_path: Path):
    data = ProjectData(name="gsOfficeBuildingPillar", version="v01")
    data.reconstruction_qc_info["state"] = "READY"
    data.reconstruction_qc_info["registeredImages"] = 293
    write_project_json(tmp_path, data)

    loaded = read_project_json(tmp_path)
    assert loaded.reconstruction_qc_info["state"] == "READY"
    assert loaded.reconstruction_qc_info["registeredImages"] == 293


def test_reconstruction_qc_section_defaults_when_absent(tmp_path: Path):
    # A project.json written before Phase 05 existed has no
    # "reconstructionQC" key at all -- reading it must not raise, and
    # must fall back to sane defaults.
    import json

    data = ProjectData(name="gsOfficeBuildingPillar", version="v01")
    raw = data.to_dict()
    del raw["reconstructionQC"]
    (tmp_path / "project.json").write_text(json.dumps(raw), encoding="utf-8")

    loaded = read_project_json(tmp_path)
    assert loaded.reconstruction_qc_info["state"] == "NOT_READY"
