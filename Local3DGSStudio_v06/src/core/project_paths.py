"""The single source of truth for turning project-relative paths into
absolute filesystem paths.

Per the architecture rule in the specification: *no GUI code, and no other
core module, should ever concatenate ``projectRoot`` with a sub-path by
hand.* Everything goes through ``ProjectPathResolver`` so that moving a
project to a different drive only ever requires updating ``projectRoot``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RelativeProjectPaths:
    """The fixed set of project-relative paths, as stored in project.json.

    These are always relative (using OS-native separators once resolved)
    and must never contain the project root themselves.
    """

    raw_data: str = "rawData"
    images: str = "rawData/images/v01"
    videos: str = "rawData/videos"
    colmap: str = "colmap/v01"
    lichtfeld: str = "lichtFeld/v01"
    point_cloud_export: str = "export/pointCloud"
    splats_export: str = "export/splats"
    renders: str = "renders"
    logs: str = "logs"

    @classmethod
    def for_version(cls, version: str) -> "RelativeProjectPaths":
        """Build the relative-path set for a given version, e.g. 'v01'."""
        return cls(
            images=f"rawData/images/{version}",
            colmap=f"colmap/{version}",
            lichtfeld=f"lichtFeld/{version}",
        )

    def to_dict(self) -> dict:
        return {
            "rawData": self.raw_data,
            "images": self.images,
            "videos": self.videos,
            "colmap": self.colmap,
            "lichtFeld": self.lichtfeld,
            "pointCloudExport": self.point_cloud_export,
            "splatsExport": self.splats_export,
            "renders": self.renders,
            "logs": self.logs,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RelativeProjectPaths":
        return cls(
            raw_data=data.get("rawData", "rawData"),
            images=data.get("images", "rawData/images/v01"),
            videos=data.get("videos", "rawData/videos"),
            colmap=data.get("colmap", "colmap/v01"),
            lichtfeld=data.get("lichtFeld", "lichtFeld/v01"),
            point_cloud_export=data.get("pointCloudExport", "export/pointCloud"),
            splats_export=data.get("splatsExport", "export/splats"),
            renders=data.get("renders", "renders"),
            logs=data.get("logs", "logs"),
        )


class ProjectPathResolver:
    """Resolves project-relative paths against an absolute project root.

    ``project_root`` is the *only* absolute path stored for a project.
    Every other path is resolved on demand, so relocating the whole project
    folder (even to a different drive letter) never breaks anything as
    long as ``project_root`` is updated to match.
    """

    def __init__(self, project_root: Path, relative_paths: RelativeProjectPaths) -> None:
        self.project_root = Path(project_root)
        self.relative_paths = relative_paths

    def resolve(self, relative_path: str) -> Path:
        """Resolve an arbitrary project-relative path string to absolute."""
        return (self.project_root / relative_path).resolve()

    @property
    def raw_data(self) -> Path:
        return self.resolve(self.relative_paths.raw_data)

    @property
    def images(self) -> Path:
        return self.resolve(self.relative_paths.images)

    @property
    def videos(self) -> Path:
        return self.resolve(self.relative_paths.videos)

    @property
    def colmap(self) -> Path:
        return self.resolve(self.relative_paths.colmap)

    @property
    def lichtfeld(self) -> Path:
        return self.resolve(self.relative_paths.lichtfeld)

    @property
    def point_cloud_export(self) -> Path:
        return self.resolve(self.relative_paths.point_cloud_export)

    @property
    def splats_export(self) -> Path:
        return self.resolve(self.relative_paths.splats_export)

    @property
    def renders(self) -> Path:
        return self.resolve(self.relative_paths.renders)

    @property
    def logs(self) -> Path:
        return self.resolve(self.relative_paths.logs)

    def all_required_directories(self) -> list[Path]:
        """Every directory that a freshly created project must contain.

        Deliberately does NOT include ``colmap/vNN/images`` -- COLMAP
        reads images directly from ``rawData/images/vNN``, so no
        persistent junction directory is part of the permanent
        structure."""
        rp = self.relative_paths
        relative_dirs = [
            rp.raw_data,
            rp.images,
            rp.videos,
            rp.colmap,
            rp.lichtfeld,
            rp.point_cloud_export,
            rp.splats_export,
            rp.renders,
            rp.logs,
            "export",  # parent of pointCloudExport / splatsExport
        ]
        return [self.resolve(d) for d in relative_dirs]

    def images_dir_for_version(self, version: str) -> Path:
        return self.resolve(f"rawData/images/{version}")

    def colmap_dir_for_version(self, version: str) -> Path:
        return self.resolve(f"colmap/{version}")

    def lichtfeld_dir_for_version(self, version: str) -> Path:
        return self.resolve(f"lichtFeld/{version}")
