from pathlib import Path

from PIL import Image

from src.core.image_validator import (
    STATUS_INVALID,
    STATUS_VALID,
    STATUS_WARNING,
    ImageValidator,
)


def _make_image(path: Path, size=(800, 600), color=(255, 0, 0)) -> None:
    Image.new("RGB", size, color).save(path)


def test_supported_image_formats_are_accepted(tmp_path: Path):
    validator = ImageValidator()
    for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
        path = tmp_path / f"photo{ext}"
        _make_image(path)
        record = validator.validate_file(path)
        assert record.status in (STATUS_VALID, STATUS_WARNING)


def test_case_insensitive_extensions(tmp_path: Path):
    validator = ImageValidator()
    path = tmp_path / "photo.JPG"
    _make_image(path)
    record = validator.validate_file(path)
    assert record.status == STATUS_VALID


def test_valid_image_passes(tmp_path: Path):
    validator = ImageValidator()
    path = tmp_path / "good.jpg"
    _make_image(path, size=(1920, 1080))
    record = validator.validate_file(path)
    assert record.status == STATUS_VALID
    assert record.width == 1920
    assert record.height == 1080
    assert record.sha256


def test_corrupt_image_detected(tmp_path: Path):
    validator = ImageValidator()
    path = tmp_path / "corrupt.jpg"
    path.write_bytes(b"not a real jpeg file at all, just garbage bytes")
    record = validator.validate_file(path)
    assert record.status == STATUS_INVALID
    assert any("Corrupt" in issue for issue in record.issues)


def test_unsupported_format_reported(tmp_path: Path):
    validator = ImageValidator()
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    record = validator.validate_file(path)
    assert record.status == STATUS_INVALID
    assert any("Unsupported" in issue for issue in record.issues)


def test_zero_byte_file_is_invalid(tmp_path: Path):
    validator = ImageValidator()
    path = tmp_path / "empty.jpg"
    path.touch()
    record = validator.validate_file(path)
    assert record.status == STATUS_INVALID
    assert any("Zero-byte" in issue for issue in record.issues)


def test_resolution_detection_matches_actual_file(tmp_path: Path):
    validator = ImageValidator()
    path = tmp_path / "wide.jpg"
    _make_image(path, size=(3840, 2160))
    record = validator.validate_file(path)
    assert record.width == 3840
    assert record.height == 2160


def test_low_resolution_is_warning_not_rejection(tmp_path: Path):
    validator = ImageValidator()
    path = tmp_path / "small.jpg"
    _make_image(path, size=(320, 240))
    record = validator.validate_file(path)
    assert record.status == STATUS_WARNING
    assert any("resolution" in issue.lower() for issue in record.issues)


def test_file_size_detection(tmp_path: Path):
    validator = ImageValidator()
    path = tmp_path / "sized.jpg"
    _make_image(path, size=(1000, 1000))
    record = validator.validate_file(path)
    assert record.file_size_bytes == path.stat().st_size
    assert record.file_size_bytes > 0


def test_duplicate_filename_detected(tmp_path: Path):
    validator = ImageValidator()
    dir_a = tmp_path / "images"
    dir_a.mkdir()
    _make_image(dir_a / "photo.jpg", color=(255, 0, 0))
    _make_image(dir_a / "PHOTO.JPG", color=(0, 255, 0))

    records, summary = validator.validate_directory(dir_a)
    assert summary.duplicate_images >= 2


def test_duplicate_image_content_detected_via_sha256(tmp_path: Path):
    validator = ImageValidator()
    directory = tmp_path / "images"
    directory.mkdir()
    _make_image(directory / "a.jpg", size=(800, 600), color=(10, 20, 30))
    _make_image(directory / "b.jpg", size=(800, 600), color=(10, 20, 30))
    _make_image(directory / "c.jpg", size=(800, 600), color=(99, 88, 77))

    records, summary = validator.validate_directory(directory)
    a = next(r for r in records if r.filename == "a.jpg")
    b = next(r for r in records if r.filename == "b.jpg")
    c = next(r for r in records if r.filename == "c.jpg")

    assert a.sha256 == b.sha256
    assert a.sha256 != c.sha256
    assert summary.duplicate_images == 2
    assert not path_has_no_deletion_side_effect(directory)  # sanity: files untouched below


def path_has_no_deletion_side_effect(directory: Path) -> bool:
    """Helper asserting validation never deletes anything; returns False
    (i.e. 'not missing') when all three files are still present."""
    names = {p.name for p in directory.iterdir()}
    return not {"a.jpg", "b.jpg", "c.jpg"}.issubset(names)


def test_validation_summary_accurate_counts(tmp_path: Path):
    validator = ImageValidator()
    directory = tmp_path / "images"
    directory.mkdir()
    _make_image(directory / "good1.jpg", size=(1920, 1080), color=(255, 0, 0))
    _make_image(directory / "good2.jpg", size=(1920, 1080), color=(0, 0, 255))
    _make_image(directory / "low_res.jpg", size=(320, 240))
    (directory / "zero.jpg").touch()
    (directory / "corrupt.png").write_bytes(b"garbage")

    records, summary = validator.validate_directory(directory)

    assert summary.total_images == 5
    assert summary.valid_images == 2
    assert summary.warning_images == 1
    assert summary.invalid_images == 2
    assert summary.overall_status == STATUS_INVALID
    assert summary.total_size_bytes == sum(r.file_size_bytes for r in records)


def test_validate_directory_on_missing_directory_returns_invalid(tmp_path: Path):
    validator = ImageValidator()
    records, summary = validator.validate_directory(tmp_path / "doesNotExist")
    assert records == []
    assert summary.total_images == 0


def test_validate_directory_progress_callback_invoked(tmp_path: Path):
    validator = ImageValidator()
    directory = tmp_path / "images"
    directory.mkdir()
    _make_image(directory / "a.jpg")
    _make_image(directory / "b.jpg")

    calls = []
    validator.validate_directory(
        directory, progress_callback=lambda cur, total, name: calls.append((cur, total, name))
    )

    assert len(calls) == 2
    assert calls[-1][0] == 2
    assert calls[-1][1] == 2


def test_validate_directory_can_be_cancelled_early(tmp_path: Path):
    validator = ImageValidator()
    directory = tmp_path / "images"
    directory.mkdir()
    for i in range(5):
        _make_image(directory / f"img{i}.jpg")

    records, summary = validator.validate_directory(
        directory, cancel_check=lambda: True
    )
    assert len(records) == 0
