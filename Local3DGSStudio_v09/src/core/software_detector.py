"""Auto-detection of external tools: COLMAP, LichtFeld Studio, FFmpeg.

Detection is best-effort and always overridable by the user in Settings.
Nothing here executes the tools -- it only checks for their presence.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

# Known default install locations, per the specification. These are only
# a starting guess -- if they don't exist, we fall back to PATH lookup.
_KNOWN_DEFAULTS = {
    "colmap": r"J:\AssetLibrary\software\3DGS\colmap_v04_02_00\COLMAP.bat",
    "lichtfeld": r"J:\AssetLibrary\software\3DGS\lichtFeld_Studio\bin\LichtFeld-Studio.exe",
}

_PATH_EXECUTABLE_NAMES = {
    "colmap": ["COLMAP.bat", "colmap.exe", "colmap"],
    "lichtfeld": ["LichtFeld-Studio.exe", "lichtfeld-studio"],
    "ffmpeg": ["ffmpeg.exe", "ffmpeg"],
}


@dataclass
class DetectionResult:
    name: str
    found: bool
    path: str = ""
    source: str = ""  # "known_default" | "path" | "manual" | ""


def detect_software(name: str, manual_override: str = "") -> DetectionResult:
    """Detect one tool by name ('colmap', 'lichtfeld', or 'ffmpeg').

    Priority: manual override (if it exists) > known default install path
    > PATH lookup.
    """
    if manual_override:
        if Path(manual_override).exists():
            return DetectionResult(name=name, found=True, path=manual_override, source="manual")

    known_default = _KNOWN_DEFAULTS.get(name, "")
    if known_default and Path(known_default).exists():
        return DetectionResult(name=name, found=True, path=known_default, source="known_default")

    for exe_name in _PATH_EXECUTABLE_NAMES.get(name, []):
        found = shutil.which(exe_name)
        if found:
            return DetectionResult(name=name, found=True, path=found, source="path")

    return DetectionResult(name=name, found=False, path="", source="")


def detect_all(manual_overrides: dict[str, str] | None = None) -> dict[str, DetectionResult]:
    overrides = manual_overrides or {}
    return {
        name: detect_software(name, overrides.get(name, ""))
        for name in ("colmap", "lichtfeld", "ffmpeg")
    }
