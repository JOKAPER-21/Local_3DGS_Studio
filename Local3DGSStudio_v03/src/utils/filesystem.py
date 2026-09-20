"""Small filesystem helpers built on pathlib.

Nothing here ever deletes, moves, or renames anything that could be user
source data -- that logic lives only in ProjectStructureManager, guarded
explicitly, per the source-protection requirement in the specification.
"""

from __future__ import annotations

from pathlib import Path


def ensure_directory(path: Path) -> bool:
    """Create ``path`` (and parents) if it does not already exist.

    Returns True if the directory was created, False if it already existed.
    """
    if path.exists():
        if not path.is_dir():
            raise NotADirectoryError(f"Path exists and is not a directory: {path}")
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def directory_is_empty(path: Path) -> bool:
    """Return True if ``path`` exists and contains no entries."""
    if not path.exists():
        return True
    return not any(path.iterdir())


def human_readable_size(num_bytes: int) -> str:
    """Format a byte count as a short human-readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"
