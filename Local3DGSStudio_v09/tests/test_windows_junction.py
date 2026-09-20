from pathlib import Path

from src.utils.windows_junction import (
    JUNCTION_ALREADY_VALID,
    JUNCTION_CONFLICT,
    JUNCTION_CREATED,
    JUNCTION_ERROR,
    ensure_image_junction,
)


def test_creates_junction_when_target_missing(tmp_path: Path):
    source = tmp_path / "rawData" / "images" / "v01"
    source.mkdir(parents=True)
    (source / "photo.jpg").write_bytes(b"data")
    target = tmp_path / "colmap" / "v01" / "images"

    result = ensure_image_junction(source, target)

    assert result.status == JUNCTION_CREATED
    assert target.is_dir()
    assert (target / "photo.jpg").exists()


def test_does_not_recreate_already_valid_junction(tmp_path: Path):
    source = tmp_path / "rawData" / "images" / "v01"
    source.mkdir(parents=True)
    target = tmp_path / "colmap" / "v01" / "images"

    first = ensure_image_junction(source, target)
    second = ensure_image_junction(source, target)

    assert first.status == JUNCTION_CREATED
    assert second.status == JUNCTION_ALREADY_VALID


def test_reports_conflict_without_deleting_real_directory(tmp_path: Path):
    source = tmp_path / "rawData" / "images" / "v01"
    source.mkdir(parents=True)

    target = tmp_path / "colmap" / "v01" / "images"
    target.mkdir(parents=True)
    marker = target / "do_not_delete.txt"
    marker.write_text("important")

    result = ensure_image_junction(source, target)

    assert result.status == JUNCTION_CONFLICT
    assert marker.exists()  # never touched
    assert marker.read_text() == "important"


def test_missing_source_is_an_error(tmp_path: Path):
    source = tmp_path / "doesNotExist"
    target = tmp_path / "colmap" / "v01" / "images"

    result = ensure_image_junction(source, target)

    assert result.status == JUNCTION_ERROR
