"""Lightweight image inspection built on Pillow.

Never loads a full-resolution decoded image into memory just to report
its dimensions: ``Image.open`` is lazy and only reads the header until
something forces a full decode, which is exactly what ``verify()``
performs (cheaply, without allocating pixel data) for corruption checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


@dataclass
class ImageInspectionResult:
    readable: bool
    corrupt: bool
    width: int = 0
    height: int = 0
    error: str = ""


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


def is_supported_video(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def inspect_image(path: Path) -> ImageInspectionResult:
    """Attempt to open and verify an image, returning its dimensions if
    readable, or a corruption/error flag if not."""
    try:
        with Image.open(path) as img:
            width, height = img.size
            img.verify()  # cheap structural check; does not decode pixels
        return ImageInspectionResult(readable=True, corrupt=False, width=width, height=height)
    except UnidentifiedImageError as exc:
        return ImageInspectionResult(readable=False, corrupt=True, error=str(exc))
    except (OSError, ValueError) as exc:
        return ImageInspectionResult(readable=False, corrupt=True, error=str(exc))
