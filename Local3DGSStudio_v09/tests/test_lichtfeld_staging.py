from pathlib import Path

from src.core.lichtfeld_staging import cleanup_staging, create_staging, staging_root


def _make_source_images(path: Path, count: int = 3) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (path / f"img_{i:04d}.jpg").write_bytes(b"fake jpg bytes")


def _make_sparse_model(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "cameras.bin").write_bytes(b"fake cameras bin")
    (path / "images.bin").write_bytes(b"fake images bin")
    (path / "points3D.bin").write_bytes(b"fake points3D bin")


def test_staging_root_is_under_temp_and_versioned(tmp_path):
    root = staging_root("gsOfficeBuildingPillar", "v01")
    assert "Local3DGSStudio" in str(root)
    assert "lichtFeldStage" in str(root)
    assert root.name == "v01"
    assert root.parent.name == "gsOfficeBuildingPillar"


def test_create_staging_links_images_and_sparse_without_copying(tmp_path):
    images = tmp_path / "rawData" / "images" / "v01"
    sparse = tmp_path / "colmap" / "v01" / "sparse" / "0"
    _make_source_images(images)
    _make_sparse_model(sparse)

    result = create_staging(images, sparse, "testProject", "v01")

    try:
        assert result.ok
        assert result.images_accessible
        assert result.sparse_files_present
        staged_images = result.staging_root / "images"
        staged_sparse = result.staging_root / "sparse" / "0"
        assert staged_images.is_dir()
        assert (staged_images / "img_0000.jpg").is_file()
        assert (staged_sparse / "cameras.bin").is_file()
        # Never copied -- the staged image file and the source file are
        # the exact same inode reached through a symlink/junction.
        assert (staged_images / "img_0000.jpg").resolve() == (images / "img_0000.jpg").resolve()
    finally:
        cleanup_staging("testProject", "v01")


def test_create_staging_never_modifies_source(tmp_path):
    images = tmp_path / "rawData" / "images" / "v01"
    sparse = tmp_path / "colmap" / "v01" / "sparse" / "0"
    _make_source_images(images)
    _make_sparse_model(sparse)

    try:
        create_staging(images, sparse, "testProject2", "v01")
        assert len(list(images.iterdir())) == 3
        assert (sparse / "cameras.bin").read_bytes() == b"fake cameras bin"
    finally:
        cleanup_staging("testProject2", "v01")


def test_create_staging_reuses_already_valid_workspace(tmp_path):
    images = tmp_path / "rawData" / "images" / "v01"
    sparse = tmp_path / "colmap" / "v01" / "sparse" / "0"
    _make_source_images(images)
    _make_sparse_model(sparse)

    try:
        first = create_staging(images, sparse, "testProject3", "v01")
        second = create_staging(images, sparse, "testProject3", "v01")
        assert first.ok and second.ok
        assert first.images_link.status != "error"
        assert second.images_link.status == "already_valid"
    finally:
        cleanup_staging("testProject3", "v01")


def test_create_staging_fails_cleanly_when_sparse_model_incomplete(tmp_path):
    images = tmp_path / "rawData" / "images" / "v01"
    sparse = tmp_path / "colmap" / "v01" / "sparse" / "0"
    _make_source_images(images)
    sparse.mkdir(parents=True, exist_ok=True)
    (sparse / "cameras.bin").write_bytes(b"only this file exists")

    try:
        result = create_staging(images, sparse, "testProject4", "v01")
        assert not result.ok
        assert not result.sparse_files_present
        assert "sparse model" in result.error.lower() or "missing required files" in result.error.lower()
    finally:
        cleanup_staging("testProject4", "v01")


def test_cleanup_staging_removes_only_the_staging_folder_not_source(tmp_path):
    images = tmp_path / "rawData" / "images" / "v01"
    sparse = tmp_path / "colmap" / "v01" / "sparse" / "0"
    _make_source_images(images)
    _make_sparse_model(sparse)

    result = create_staging(images, sparse, "testProject5", "v01")
    assert result.staging_root.exists()

    cleanup_staging("testProject5", "v01")

    assert not result.staging_root.exists()
    assert images.exists() and len(list(images.iterdir())) == 3
    assert (sparse / "cameras.bin").exists()
