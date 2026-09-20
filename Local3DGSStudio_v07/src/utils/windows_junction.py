"""Windows directory junction creation for the COLMAP ``images`` folder.

On a real Windows deployment this uses ``mklink /J`` so hundreds of
megabytes (or more) of source images are never duplicated -- only a
lightweight reparse point is created at ``colmap/<version>/images``
pointing back at ``rawData/images/<version>``.

On non-Windows platforms (used only to develop and test this codebase)
it falls back to a plain symlink so the rest of the pipeline can still
be exercised end-to-end without a Windows machine.

This module never deletes an existing *real* directory found at the
junction target -- that is always reported back as a conflict for the
user to resolve manually, per the source-protection rules.
"""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

JUNCTION_CREATED = "created"
JUNCTION_ALREADY_VALID = "already_valid"
JUNCTION_CONFLICT = "conflict"
JUNCTION_ERROR = "error"


@dataclass
class JunctionResult:
    status: str
    target: Path
    source: Path
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (JUNCTION_CREATED, JUNCTION_ALREADY_VALID)


def is_windows() -> bool:
    return platform.system() == "Windows"


def _points_to(target: Path, source: Path) -> bool:
    try:
        return target.resolve() == source.resolve()
    except OSError:
        return False


def ensure_image_junction(source: Path, target: Path) -> JunctionResult:
    """Create (or verify) a junction at ``target`` pointing at ``source``.

    Returns without touching anything if ``target`` already exists and
    correctly points at ``source`` (never recreates an already-valid
    junction unnecessarily). If ``target`` exists as something else (a
    real directory, a broken link, or a link to a different source), that
    is reported as a conflict -- nothing is deleted automatically.
    """
    if not source.is_dir():
        return JunctionResult(
            JUNCTION_ERROR, target, source, f"Source directory does not exist: {source}"
        )

    if target.exists() or target.is_symlink():
        if _points_to(target, source):
            return JunctionResult(
                JUNCTION_ALREADY_VALID, target, source,
                "Junction already exists and points to the source directory.",
            )
        return JunctionResult(
            JUNCTION_CONFLICT, target, source,
            f"A file or directory already exists at {target} and does not point to "
            f"{source}. Resolve this manually (rename or remove it) before continuing.",
        )

    target.parent.mkdir(parents=True, exist_ok=True)

    if is_windows():
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(target), str(source)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return JunctionResult(
                JUNCTION_ERROR, target, source, (result.stderr or result.stdout).strip()
            )
        return JunctionResult(JUNCTION_CREATED, target, source, "Junction created.")

    # Non-Windows development fallback: a real Windows junction is a
    # reparse point, not a symlink, but a symlink is close enough to
    # exercise every consumer of this module during development/tests.
    try:
        target.symlink_to(source, target_is_directory=True)
    except OSError as exc:
        return JunctionResult(JUNCTION_ERROR, target, source, str(exc))
    return JunctionResult(
        JUNCTION_CREATED, target, source, "Symlink created (non-Windows development fallback)."
    )
