"""Content hashing for duplicate-image detection.

Reads files in chunks so multi-hundred-megabyte TIFFs don't get loaded
into memory whole.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024  # 1 MB


def calculate_sha256(path: Path) -> str:
    """Return the hex SHA256 digest of a file's contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
