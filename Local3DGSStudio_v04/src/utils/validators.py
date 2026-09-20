"""Validation helpers for user-supplied Projects Setup inputs.

These are pure functions with no GUI or filesystem side effects, so they
are trivial to unit test and safe to call from both the GUI layer and the
core managers.
"""

from __future__ import annotations

import re
from pathlib import Path

# Windows reserved / invalid filename characters.
_INVALID_WINDOWS_CHARS = r'<>:"/\\|?*'
_INVALID_CHARS_PATTERN = re.compile(f"[{re.escape(_INVALID_WINDOWS_CHARS)}]")

# Windows reserved device names (case-insensitive).
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_VERSION_PATTERN = re.compile(r"^v[0-9]{2}$")

# camelCase: starts lowercase, letters/digits only, no spaces, no underscores.
_PROJECT_NAME_PATTERN = re.compile(r"^[a-z][a-zA-Z0-9]*$")


class ValidationError(ValueError):
    """Raised when a user-supplied value fails validation."""


def validate_project_name(name: str) -> str:
    """Validate a project name and return it unchanged if valid.

    Rules (per specification): camelCase, no spaces, no special/invalid
    Windows filename characters, not empty, not a reserved device name.
    """
    if not name or not name.strip():
        raise ValidationError("Project name cannot be empty.")

    if " " in name:
        raise ValidationError("Project name cannot contain spaces.")

    if _INVALID_CHARS_PATTERN.search(name):
        raise ValidationError(
            f"Project name contains invalid characters. "
            f"Avoid any of: {_INVALID_WINDOWS_CHARS}"
        )

    if name.upper() in _RESERVED_NAMES:
        raise ValidationError(f"'{name}' is a reserved Windows name and cannot be used.")

    if not _PROJECT_NAME_PATTERN.match(name):
        raise ValidationError(
            "Project name must be camelCase: start with a lowercase letter and "
            "contain only letters and digits (e.g. 'gsOfficeBuildingPillar')."
        )

    return name


def validate_version(version: str) -> str:
    """Validate a version string against the required 'vXX' format."""
    if not version or not version.strip():
        raise ValidationError("Version cannot be empty.")

    if not _VERSION_PATTERN.match(version):
        raise ValidationError(
            f"Version must match the pattern 'vNN' (e.g. 'v01'). Got: '{version}'"
        )

    return version


def validate_project_root(root: str) -> Path:
    """Validate that a project root path is usable.

    The folder does not need to already exist (it may be created), but the
    path itself must be well-formed and not empty.
    """
    if not root or not root.strip():
        raise ValidationError("Project root cannot be empty.")

    path = Path(root)

    if not path.is_absolute():
        raise ValidationError("Project root must be an absolute path.")

    return path


def next_version_string(current: str) -> str:
    """Given 'v01', return 'v02'. Raises ValidationError if malformed."""
    validate_version(current)
    number = int(current[1:]) + 1
    if number > 99:
        raise ValidationError("Version numbers above v99 are not supported.")
    return f"v{number:02d}"
