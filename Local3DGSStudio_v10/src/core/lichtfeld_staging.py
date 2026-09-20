"""Temporary staging workspace for LichtFeld Studio.

LichtFeld expects a standard COLMAP dataset layout (``images/`` next to
``sparse/0/``) in one folder. This application's permanent project
structure deliberately does **not** keep such a folder around --
``rawData/images/vNN`` is the one and only permanent source of truth for
images, and ``colmap/vNN/sparse/0`` is the one and only permanent
location for the reconstruction (see the "no persistent colmap/vNN/images
junction" architecture rule).

So when (and only when) the user asks to send a reconstruction to
LichtFeld, this module builds a small *temporary* staging folder under
the OS temp directory, wires it up with two junctions/symlinks -- never
copies -- and leaves the permanent project untouched. The staging folder
can be safely deleted at any time; it holds no data of its own.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.utils.windows_junction import JunctionResult, ensure_image_junction

STAGING_APP_DIR = "Local3DGSStudio"
STAGING_SUBDIR = "lichtFeldStage"

_INVALID_PATH_CHARS = '<>:"/\\|?*'


@dataclass
class StagingResult:
    staging_root: Path
    images_link: JunctionResult
    sparse_link: JunctionResult
    images_accessible: bool = False
    sparse_files_present: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return (
            not self.error
            and self.images_link.ok
            and self.sparse_link.ok
            and self.images_accessible
            and self.sparse_files_present
        )


def _sanitize(name: str) -> str:
    cleaned = "".join(c for c in name if c not in _INVALID_PATH_CHARS)
    return cleaned or "project"


def staging_root(project_name: str, version: str) -> Path:
    """``%TEMP%/Local3DGSStudio/lichtFeldStage/<project>/<version>``."""
    base = Path(tempfile.gettempdir()) / STAGING_APP_DIR / STAGING_SUBDIR
    return base / _sanitize(project_name) / _sanitize(version)


def create_staging(
    image_source: Path, sparse_model: Path, project_name: str, version: str
) -> StagingResult:
    """Build (or reuse) the temporary staging workspace for one project
    version. Never copies source images or the sparse model -- only
    creates junctions/symlinks pointing back at the permanent, real
    locations. Safe to call repeatedly; an already-valid staging
    workspace is left alone rather than recreated."""
    root = staging_root(project_name, version)
    images_target = root / "images"
    sparse_parent = root / "sparse"
    sparse_target = sparse_parent / "0"

    images_link = ensure_image_junction(image_source, images_target)
    # `ensure_image_junction` is generic despite its name (source/target
    # are plain parameters) -- reused here for the sparse model link too,
    # rather than duplicating junction/symlink logic.
    sparse_link = ensure_image_junction(sparse_model, sparse_target)

    images_accessible = (
        images_target.is_dir() and any(p.is_file() for p in images_target.iterdir())
        if images_link.ok
        else False
    )

    sparse_files_present = sparse_link.ok and all(
        (sparse_target / name).is_file() for name in ("cameras.bin", "images.bin", "points3D.bin")
    )

    error = ""
    if not images_link.ok:
        error = f"Image staging failed: {images_link.message}"
    elif not sparse_link.ok:
        error = f"Sparse model staging failed: {sparse_link.message}"
    elif not images_accessible:
        error = f"Staged image directory is empty or inaccessible: {images_target}"
    elif not sparse_files_present:
        error = f"Staged sparse model is missing required files at: {sparse_target}"

    return StagingResult(
        staging_root=root,
        images_link=images_link,
        sparse_link=sparse_link,
        images_accessible=images_accessible,
        sparse_files_present=sparse_files_present,
        error=error,
    )


def cleanup_staging(project_name: str, version: str) -> None:
    """Remove a staging workspace. Only ever removes the *staging*
    folder itself (which holds nothing but junctions/symlinks) -- never
    touches what those links point at."""
    root = staging_root(project_name, version)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
