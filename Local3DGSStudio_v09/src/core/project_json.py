"""``project.json`` data model.

``ProjectData`` mirrors the required-fields shape from the specification.
Only ``projectRoot`` is ever stored as an absolute path (and it is stored
outside this file, held by the resolver/manager); everything under
``paths`` here is relative, per the portability rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.project_paths import RelativeProjectPaths

APP_NAME = "Local3DGSStudio"
APP_VERSION = "0.1.0"
PROJECT_JSON_FILENAME = "project.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ProjectData:
    name: str
    version: str
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = field(default_factory=_now_iso)

    relative_paths: RelativeProjectPaths = field(default_factory=RelativeProjectPaths)

    external_software: dict = field(default_factory=lambda: {
        "colmap": {"path": ""},
        "lichtfeld": {"path": ""},
        "ffmpeg": {"path": ""},
    })

    input_info: dict = field(default_factory=lambda: {
        "imageCount": 0,
        "videoCount": 0,
        "activeImageVersion": "v01",
    })

    colmap_info: dict = field(default_factory=lambda: {
        "activeVersion": "v01",
        "database": "",
        "sparseModel": "",
        "state": "NOT_STARTED",
        "lastRun": "",
        "registeredImages": 0,
        "sparsePoints": 0,
        "observations": 0,
        "meanTrackLength": 0,
        "meanReprojectionError": 0,
        "featureExtraction": {"completed": False, "useGPU": False, "numThreads": 4},
        "featureMatching": {"completed": False, "method": "exhaustive", "useGPU": False},
        "mapper": {"completed": False},
        "analysis": {
            "completed": False,
            "registeredImages": 0,
            "totalImages": 0,
            "points": 0,
            "observations": 0,
            "meanTrackLength": 0.0,
            "meanReprojectionError": 0.0,
        },
    })

    lichtfeld_info: dict = field(default_factory=lambda: {
        "trainingStatus": "notStarted",
        "iteration": 0,
        "numSplats": 0,
    })

    export_info: dict = field(default_factory=lambda: {
        "pointCloud": [], "splats": [], "html": [], "usd": [], "spz": [], "sog": [],
    })

    render_info: dict = field(default_factory=lambda: {"renderCount": 0})

    validation_info: dict = field(default_factory=lambda: {
        "lastValidationTime": "",
        "validationStatus": "notValidated",
        "totalImages": 0,
        "validImages": 0,
        "warningImages": 0,
        "invalidImages": 0,
        "duplicateImages": 0,
    })

    reconstruction_qc_info: dict = field(default_factory=lambda: {
        "lastCheckedAt": "",
        "state": "NOT_READY",
        "totalImages": 0,
        "registeredImages": 0,
        "registrationPercentage": 0.0,
        "cameras": 0,
        "registeredCameras": 0,
        "frames": 0,
        "registeredFrames": 0,
        "points": 0,
        "observations": 0,
        "meanTrackLength": None,
        "meanObservationsPerImage": None,
        "meanReprojectionErrorPx": None,
        "cameraModels": [],
        "distortedCameraModels": [],
        "requiredFilesPresent": False,
        "databaseValid": False,
        "junctionValid": False,
        "warnings": [],
        "errors": [],
    })

    # -- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "application": {"name": APP_NAME, "version": APP_VERSION},
            "project": {
                "name": self.name,
                "version": self.version,
                "createdAt": self.created_at,
                "modifiedAt": self.modified_at,
            },
            "paths": self.relative_paths.to_dict(),
            "externalSoftware": self.external_software,
            "input": self.input_info,
            "colmap": self.colmap_info,
            "lichtfeld": self.lichtfeld_info,
            "export": self.export_info,
            "render": self.render_info,
            "validation": self.validation_info,
            "reconstructionQC": self.reconstruction_qc_info,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectData":
        project = data.get("project", {})
        return cls(
            name=project.get("name", ""),
            version=project.get("version", "v01"),
            created_at=project.get("createdAt", _now_iso()),
            modified_at=project.get("modifiedAt", _now_iso()),
            relative_paths=RelativeProjectPaths.from_dict(data.get("paths", {})),
            external_software=data.get("externalSoftware", {}) or {},
            input_info=data.get("input", {}) or {},
            colmap_info=data.get("colmap", {}) or {},
            lichtfeld_info=data.get("lichtfeld", {}) or {},
            export_info=data.get("export", {}) or {},
            render_info=data.get("render", {}) or {},
            validation_info=data.get("validation", {}) or {
                "lastValidationTime": "",
                "validationStatus": "notValidated",
                "totalImages": 0,
                "validImages": 0,
                "warningImages": 0,
                "invalidImages": 0,
                "duplicateImages": 0,
            },
            reconstruction_qc_info=data.get("reconstructionQC", {}) or {
                "lastCheckedAt": "",
                "state": "NOT_READY",
                "totalImages": 0,
                "registeredImages": 0,
                "registrationPercentage": 0.0,
                "cameras": 0,
                "registeredCameras": 0,
                "frames": 0,
                "registeredFrames": 0,
                "points": 0,
                "observations": 0,
                "meanTrackLength": None,
                "meanObservationsPerImage": None,
                "meanReprojectionErrorPx": None,
                "cameraModels": [],
                "distortedCameraModels": [],
                "requiredFilesPresent": False,
                "databaseValid": False,
                "junctionValid": False,
                "warnings": [],
                "errors": [],
            },
        )

    def touch_modified(self) -> None:
        self.modified_at = _now_iso()


class ProjectJsonError(Exception):
    """Raised when project.json is missing, unreadable, or malformed."""


def write_project_json(project_root: Path, data: ProjectData) -> Path:
    """Write ``project.json`` to disk. Never overwrites silently outside
    the caller's explicit intent -- callers decide whether overwrite is
    allowed; this function just writes the bytes."""
    target = project_root / PROJECT_JSON_FILENAME
    target.write_text(json.dumps(data.to_dict(), indent=2), encoding="utf-8")
    return target


def read_project_json(project_root: Path) -> ProjectData:
    target = project_root / PROJECT_JSON_FILENAME
    if not target.exists():
        raise ProjectJsonError(f"No project.json found at: {target}")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectJsonError(f"project.json is not valid JSON: {exc}") from exc

    if "project" not in raw or "paths" not in raw:
        raise ProjectJsonError(
            "project.json is missing required top-level fields ('project', 'paths')."
        )

    return ProjectData.from_dict(raw)
