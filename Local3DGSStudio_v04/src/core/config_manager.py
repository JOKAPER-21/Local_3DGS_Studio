"""Application-level configuration.

Stores state that is *not* part of any single project:

* the last opened project's root (so the app can auto-load it at startup)
* manually-overridden paths to external software (COLMAP, LichtFeld, FFmpeg)

Per the specification, ``last_project.json`` must live in the application's
user config directory, never inside a project folder.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

APP_DIR_NAME = "Local3DGSStudio"
LAST_PROJECT_FILENAME = "last_project.json"
APP_SETTINGS_FILENAME = "app_settings.json"


def get_app_config_dir() -> Path:
    """Return (and create) the per-user config directory for this app.

    On Windows this resolves under %APPDATA%; elsewhere it falls back to
    ``~/.config`` so the module still works for development on Linux/macOS.
    """
    base = os.environ.get("APPDATA")
    if base:
        config_dir = Path(base) / APP_DIR_NAME
    else:
        config_dir = Path.home() / ".config" / APP_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


@dataclass
class ExternalSoftwarePaths:
    colmap: str = ""
    lichtfeld: str = ""
    ffmpeg: str = ""


@dataclass
class AppSettings:
    default_project_root: str = ""
    external_software: ExternalSoftwarePaths = field(default_factory=ExternalSoftwarePaths)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        ext = data.get("external_software", {}) or {}
        return cls(
            default_project_root=data.get("default_project_root", ""),
            external_software=ExternalSoftwarePaths(
                colmap=ext.get("colmap", ""),
                lichtfeld=ext.get("lichtfeld", ""),
                ffmpeg=ext.get("ffmpeg", ""),
            ),
        )


class ConfigManager:
    """Reads/writes ``last_project.json`` and ``app_settings.json``."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self.config_dir = config_dir or get_app_config_dir()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.last_project_file = self.config_dir / LAST_PROJECT_FILENAME
        self.settings_file = self.config_dir / APP_SETTINGS_FILENAME

    # -- last opened project -------------------------------------------------

    def save_last_project(self, project_root: Path) -> None:
        data = {"lastProjectRoot": str(project_root)}
        self.last_project_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_last_project(self) -> Optional[Path]:
        if not self.last_project_file.exists():
            return None
        try:
            data = json.loads(self.last_project_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        root = data.get("lastProjectRoot")
        return Path(root) if root else None

    def clear_last_project(self) -> None:
        if self.last_project_file.exists():
            self.last_project_file.unlink()

    # -- app settings (external software paths, default project root) ------

    def load_settings(self) -> AppSettings:
        if not self.settings_file.exists():
            return AppSettings()
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return AppSettings()
        return AppSettings.from_dict(data)

    def save_settings(self, settings: AppSettings) -> None:
        self.settings_file.write_text(
            json.dumps(settings.to_dict(), indent=2), encoding="utf-8"
        )
