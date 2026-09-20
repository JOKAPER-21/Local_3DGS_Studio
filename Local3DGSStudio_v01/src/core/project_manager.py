"""``ProjectManager``: the single facade the GUI talks to for everything
project-related.

GUI code must never build paths itself or read/write project.json
directly -- it calls into this class, which owns the currently-open
project's state and delegates structure/JSON/path work to the other core
modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.config_manager import ConfigManager
from src.core.project_json import (
    ProjectData,
    ProjectJsonError,
    read_project_json,
    write_project_json,
)
from src.core.project_paths import ProjectPathResolver, RelativeProjectPaths
from src.core.project_structure import (
    ProjectAlreadyExistsError,
    ProjectStructureManager,
    StructureReport,
)
from src.utils.validators import (
    ValidationError,
    validate_project_name,
    validate_project_root,
    validate_version,
)


class ProjectLoadError(Exception):
    """Raised when a project cannot be opened or loaded."""


@dataclass
class OpenProject:
    """The full in-memory state of the currently open project."""

    project_root: Path
    data: ProjectData
    resolver: ProjectPathResolver


class ProjectManager:
    """Creates, opens, closes, and persists projects.

    Responsibilities (per spec): createProject, openProject, closeProject,
    loadProjectJson, saveProjectJson, validateProject, setActiveVersion,
    getActiveVersion, saveLastOpenedProject, loadLastOpenedProject.
    """

    def __init__(self, config_manager: Optional[ConfigManager] = None) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.structure_manager = ProjectStructureManager()
        self.current: Optional[OpenProject] = None

    # -- creation ---------------------------------------------------------

    def create_project(self, project_root: str, project_name: str, version: str) -> OpenProject:
        """One-click project creation. Validates inputs, builds the folder
        tree, writes project.json, and opens the new project.

        Raises ValidationError for bad input, or
        ProjectAlreadyExistsError if the target already contains a
        project -- existing projects are never silently overwritten.
        """
        root_path = validate_project_root(project_root)
        name = validate_project_name(project_name)
        ver = validate_version(version)

        full_project_path = root_path / name
        relative_paths = RelativeProjectPaths.for_version(ver)

        self.structure_manager.create_project(full_project_path, relative_paths)

        data = ProjectData(name=name, version=ver, relative_paths=relative_paths)
        data.input_info["activeImageVersion"] = ver
        data.colmap_info["activeVersion"] = ver
        write_project_json(full_project_path, data)

        return self.open_project(str(full_project_path))

    # -- opening / closing --------------------------------------------------

    def open_project(self, project_root: str) -> OpenProject:
        """Open an existing project folder. The user only ever selects the
        folder -- every internal path is resolved automatically from
        project.json."""
        root_path = Path(project_root)
        if not root_path.exists():
            raise ProjectLoadError(f"Project folder does not exist: {root_path}")

        try:
            data = read_project_json(root_path)
        except ProjectJsonError as exc:
            raise ProjectLoadError(str(exc)) from exc

        resolver = ProjectPathResolver(root_path, data.relative_paths)
        self.current = OpenProject(project_root=root_path, data=data, resolver=resolver)
        self.save_last_opened_project(root_path)
        return self.current

    def close_project(self) -> None:
        self.current = None

    # -- validation / repair -------------------------------------------------

    def validate_current_project(self) -> StructureReport:
        if self.current is None:
            raise ProjectLoadError("No project is currently open.")
        return self.structure_manager.validate_project(
            self.current.project_root, self.current.data.relative_paths
        )

    def repair_current_project(self) -> StructureReport:
        if self.current is None:
            raise ProjectLoadError("No project is currently open.")
        return self.structure_manager.repair_project(
            self.current.project_root, self.current.data.relative_paths
        )

    # -- persistence --------------------------------------------------------

    def save_project_json(self) -> None:
        if self.current is None:
            raise ProjectLoadError("No project is currently open.")
        self.current.data.touch_modified()
        write_project_json(self.current.project_root, self.current.data)

    # -- versioning (stub-level for phase01/02) ------------------------------

    def get_active_version(self) -> str:
        if self.current is None:
            raise ProjectLoadError("No project is currently open.")
        return self.current.data.version

    def set_active_version(self, version: str) -> None:
        """Create (if needed) and switch to a new version's folders,
        without touching or duplicating any previous version."""
        if self.current is None:
            raise ProjectLoadError("No project is currently open.")
        validate_version(version)

        self.structure_manager.create_version(self.current.project_root, version)

        self.current.data.relative_paths = RelativeProjectPaths.for_version(version)
        self.current.data.version = version
        self.current.data.input_info["activeImageVersion"] = version
        self.current.data.colmap_info["activeVersion"] = version
        self.current.resolver = ProjectPathResolver(
            self.current.project_root, self.current.data.relative_paths
        )
        self.save_project_json()

    # -- last-opened-project memory ------------------------------------------

    def save_last_opened_project(self, project_root: Path) -> None:
        self.config_manager.save_last_project(project_root)

    def load_last_opened_project(self) -> Optional[OpenProject]:
        """Attempt to auto-load the last opened project at startup.

        Returns None (without raising) if there is no remembered project,
        or if it no longer exists / is invalid -- callers should show the
        appropriate "missing project" or "invalid project" prompt in that
        case, per the specification's startup behavior.
        """
        last_root = self.config_manager.load_last_project()
        if last_root is None:
            return None
        if not last_root.exists():
            return None
        try:
            return self.open_project(str(last_root))
        except ProjectLoadError:
            return None
