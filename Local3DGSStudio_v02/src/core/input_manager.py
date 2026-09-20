"""``InputManager``: resolves and lists the active project's input data.

Every path here comes from the already-open project's
``ProjectPathResolver`` (via ``ProjectManager``) -- this module never
constructs a path by hand and never asks the user to browse for the
image or video directory of an existing project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.core.project_manager import ProjectLoadError, ProjectManager
from src.utils.image_utils import is_supported_image, is_supported_video

_VERSION_DIR_PATTERN = re.compile(r"^v([0-9]{2})$")


@dataclass
class ImageFileInfo:
    filename: str
    extension: str
    absolute_path: Path
    relative_path: str
    file_size_bytes: int
    modified_time: float


@dataclass
class VideoFileInfo:
    filename: str
    extension: str
    absolute_path: Path
    relative_path: str
    file_size_bytes: int
    modified_time: float


class InputManager:
    """Manages the active project's ``rawData/images`` and
    ``rawData/videos`` without ever modifying the source files.

    Responsibilities (per spec): resolveActiveImageDirectory,
    resolveVideoDirectory, listImages, listVideos, countImages,
    countVideos, getImageInformation, getVideoInformation,
    createImageVersion, refreshInputData.
    """

    def __init__(self, project_manager: ProjectManager) -> None:
        self.project_manager = project_manager

    def _require_current(self):
        if self.project_manager.current is None:
            raise ProjectLoadError("No project is currently open.")
        return self.project_manager.current

    # -- directory resolution ------------------------------------------------

    def get_active_image_directory(self) -> Path:
        """Resolved absolute path to the active version's image folder."""
        return self._require_current().resolver.images

    def get_video_directory(self) -> Path:
        """Resolved absolute path to the project's (version-independent)
        video folder."""
        return self._require_current().resolver.videos

    # -- listing --------------------------------------------------------------

    def list_images(self) -> list[ImageFileInfo]:
        directory = self.get_active_image_directory()
        if not directory.is_dir():
            return []

        results: list[ImageFileInfo] = []
        for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_file() or not is_supported_image(entry):
                continue
            stat = entry.stat()
            results.append(
                ImageFileInfo(
                    filename=entry.name,
                    extension=entry.suffix.lower(),
                    absolute_path=entry,
                    relative_path=str(entry.relative_to(self._require_current().project_root)),
                    file_size_bytes=stat.st_size,
                    modified_time=stat.st_mtime,
                )
            )
        return results

    def list_videos(self) -> list[VideoFileInfo]:
        directory = self.get_video_directory()
        if not directory.is_dir():
            return []

        results: list[VideoFileInfo] = []
        for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_file() or not is_supported_video(entry):
                continue
            stat = entry.stat()
            results.append(
                VideoFileInfo(
                    filename=entry.name,
                    extension=entry.suffix.lower(),
                    absolute_path=entry,
                    relative_path=str(entry.relative_to(self._require_current().project_root)),
                    file_size_bytes=stat.st_size,
                    modified_time=stat.st_mtime,
                )
            )
        return results

    # -- counting -------------------------------------------------------------

    def count_images(self) -> int:
        return len(self.list_images())

    def count_videos(self) -> int:
        return len(self.list_videos())

    # -- per-file information --------------------------------------------------

    def get_image_information(self, filename: str) -> ImageFileInfo | None:
        for info in self.list_images():
            if info.filename == filename:
                return info
        return None

    def get_video_information(self, filename: str) -> VideoFileInfo | None:
        for info in self.list_videos():
            if info.filename == filename:
                return info
        return None

    # -- refresh: sync project.json's cached counts with reality ----------------

    def refresh_input_data(self) -> None:
        """Recount images/videos from disk and persist the counts into
        project.json (imageCount, videoCount, modifiedAt)."""
        current = self._require_current()
        current.data.input_info["imageCount"] = self.count_images()
        current.data.input_info["videoCount"] = self.count_videos()
        current.data.input_info["activeImageVersion"] = current.data.version
        self.project_manager.save_project_json()

    # -- versioning -------------------------------------------------------------

    def _existing_version_numbers(self) -> list[int]:
        current = self._require_current()
        images_root = current.resolver.resolve(current.data.relative_paths.raw_data) / "images"
        if not images_root.is_dir():
            return []
        numbers = []
        for entry in images_root.iterdir():
            if entry.is_dir():
                match = _VERSION_DIR_PATTERN.match(entry.name)
                if match:
                    numbers.append(int(match.group(1)))
        return numbers

    def next_version_string(self) -> str:
        """Scan existing version folders and return the next 'vNN'."""
        existing = self._existing_version_numbers()
        highest = max(existing) if existing else int(self._require_current().data.version[1:])
        return f"v{highest + 1:02d}"

    def create_image_version(self, version: str | None = None) -> str:
        """Create image + COLMAP directories for a new version (or the
        auto-computed next version), set it active, and persist
        project.json. Never touches any previous version's folders."""
        new_version = version or self.next_version_string()
        self.project_manager.set_active_version(new_version)
        self.refresh_input_data()
        return new_version
