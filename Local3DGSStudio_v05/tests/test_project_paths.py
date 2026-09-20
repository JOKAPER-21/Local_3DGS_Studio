from pathlib import Path

from src.core.project_paths import ProjectPathResolver, RelativeProjectPaths


def test_resolver_resolves_all_known_paths(tmp_path: Path):
    relative = RelativeProjectPaths.for_version("v01")
    resolver = ProjectPathResolver(tmp_path, relative)

    assert resolver.images == (tmp_path / "rawData" / "images" / "v01").resolve()
    assert resolver.colmap == (tmp_path / "colmap" / "v01").resolve()
    assert resolver.videos == (tmp_path / "rawData" / "videos").resolve()
    assert resolver.point_cloud_export == (tmp_path / "export" / "pointCloud").resolve()
    assert resolver.splats_export == (tmp_path / "export" / "splats").resolve()
    assert resolver.renders == (tmp_path / "renders").resolve()
    assert resolver.logs == (tmp_path / "logs").resolve()


def test_moving_project_root_only_requires_changing_root(tmp_path: Path):
    """Simulates relocating a whole project: only projectRoot changes,
    every resolved path updates automatically."""
    relative = RelativeProjectPaths.for_version("v01")

    old_root = tmp_path / "old_drive" / "myProject"
    new_root = tmp_path / "new_drive" / "myProject"

    old_resolver = ProjectPathResolver(old_root, relative)
    new_resolver = ProjectPathResolver(new_root, relative)

    # The relative suffix under images/colmap is identical either way.
    assert old_resolver.images.relative_to(old_root) == new_resolver.images.relative_to(new_root)
    assert old_resolver.colmap.relative_to(old_root) == new_resolver.colmap.relative_to(new_root)


def test_all_required_directories_includes_export_parent(tmp_path: Path):
    relative = RelativeProjectPaths.for_version("v01")
    resolver = ProjectPathResolver(tmp_path, relative)
    required = resolver.all_required_directories()

    assert resolver.point_cloud_export in required
    assert resolver.splats_export in required
    assert (tmp_path / "export").resolve() in required


def test_for_version_only_changes_images_and_colmap():
    v1 = RelativeProjectPaths.for_version("v01")
    v2 = RelativeProjectPaths.for_version("v02")

    assert v1.images != v2.images
    assert v1.colmap != v2.colmap
    assert v1.videos == v2.videos
    assert v1.renders == v2.renders
