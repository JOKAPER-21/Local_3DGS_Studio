"""``ProjectStructureManager``: creates, validates, and repairs the on-disk
folder layout of a project.

This module never deletes, moves, or renames anything. Its only
destructive-adjacent capability is directory *creation*, which is always
additive and safe to repeat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.core.project_paths import ProjectPathResolver, RelativeProjectPaths
from src.utils.filesystem import ensure_directory


class ProjectAlreadyExistsError(Exception):
    """Raised when creating a project whose folder already contains one."""


@dataclass
class StructureReport:
    """Result of validating (or creating) a project's folder structure."""

    project_root: Path
    created_directories: list[Path] = field(default_factory=list)
    existing_directories: list[Path] = field(default_factory=list)
    missing_directories: list[Path] = field(default_factory=list)
    project_json_exists: bool = False

    @property
    def is_valid(self) -> bool:
        return not self.missing_directories and self.project_json_exists

    @property
    def all_required_directories(self) -> list[Path]:
        return self.created_directories + self.existing_directories + self.missing_directories


class ProjectStructureManager:
    """Creates and validates the standard project folder layout.

    Required responsibilities (per spec): createProjectStructure,
    validateProjectStructure, createVersionDirectories,
    checkRequiredDirectories, checkRequiredFiles,
    reportMissingDirectories, repairMissingDirectories.
    """

    def project_already_exists(self, project_root: Path) -> bool:
        """A project 'exists' if its root folder is present and non-empty,
        or if it already contains a project.json."""
        if not project_root.exists():
            return False
        if (project_root / "project.json").exists():
            return True
        return project_root.is_dir() and any(project_root.iterdir())

    def create_project(
        self,
        project_root: Path,
        relative_paths: RelativeProjectPaths,
        allow_existing_empty_folder: bool = True,
    ) -> StructureReport:
        """Create the full directory tree for a brand-new project.

        Raises ``ProjectAlreadyExistsError`` if the target already looks
        like a project or contains files, so an existing project is never
        silently overwritten.
        """
        if self.project_already_exists(project_root):
            raise ProjectAlreadyExistsError(
                f"A project already exists at: {project_root}"
            )
        if project_root.exists() and not allow_existing_empty_folder:
            raise ProjectAlreadyExistsError(
                f"Target folder already exists: {project_root}"
            )

        resolver = ProjectPathResolver(project_root, relative_paths)
        report = StructureReport(project_root=project_root)

        ensure_directory(project_root)
        for directory in resolver.all_required_directories():
            if ensure_directory(directory):
                report.created_directories.append(directory)
            else:
                report.existing_directories.append(directory)

        return report

    def validate_project(
        self, project_root: Path, relative_paths: RelativeProjectPaths
    ) -> StructureReport:
        """Check that every required directory and project.json exist,
        without creating anything."""
        resolver = ProjectPathResolver(project_root, relative_paths)
        report = StructureReport(project_root=project_root)

        for directory in resolver.all_required_directories():
            if directory.is_dir():
                report.existing_directories.append(directory)
            else:
                report.missing_directories.append(directory)

        report.project_json_exists = (project_root / "project.json").exists()
        return report

    def repair_project(
        self, project_root: Path, relative_paths: RelativeProjectPaths
    ) -> StructureReport:
        """Create any missing required directories. Never touches existing
        files or directories, and never regenerates project.json (that is
        the caller's decision, handled by ProjectManager)."""
        resolver = ProjectPathResolver(project_root, relative_paths)
        report = StructureReport(project_root=project_root)

        for directory in resolver.all_required_directories():
            if ensure_directory(directory):
                report.created_directories.append(directory)
            else:
                report.existing_directories.append(directory)

        report.project_json_exists = (project_root / "project.json").exists()
        return report

    def create_version(
        self, project_root: Path, version: str
    ) -> tuple[Path, Path]:
        """Create the images/COLMAP directories for a new version, leaving
        every previous version's folders untouched. Returns
        (images_dir, colmap_dir)."""
        relative_paths = RelativeProjectPaths.for_version(version)
        resolver = ProjectPathResolver(project_root, relative_paths)
        ensure_directory(resolver.images)
        ensure_directory(resolver.colmap)
        return resolver.images, resolver.colmap
