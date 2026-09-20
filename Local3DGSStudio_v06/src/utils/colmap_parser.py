"""Parsing helpers for raw COLMAP CLI output and binary model files.

Kept separate from ``COLMAPManager`` / the GUI so the exact regexes (and
the ``cameras.bin`` reader) can be unit tested against real captured
COLMAP output/files without needing a COLMAP installation or a Qt event
loop.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

_VERSION_PATTERN = re.compile(r"COLMAP\s+([0-9]+\.[0-9]+\.[0-9]+)")
_CUDA_PATTERN = re.compile(r"with\s+CUDA", re.IGNORECASE)

# model_analyzer prints lines like "Registered images: 293" or
# "Mean reprojection error: 0.937114px". Values may be int or float, and
# a trailing unit (e.g. "px") is tolerated but not captured.
#
# Deliberately NOT anchored to the start of a line: real COLMAP (glog)
# output prefixes every line with a timestamp/thread/source-location
# header (e.g. "I0917 12:00:00.123456 12345 model_analyzer.cc:73] "), so
# an anchored "^\s*Cameras:" pattern never matches against genuine COLMAP
# output even though it matches hand-written test fixtures without that
# prefix. Searching for the label anywhere in the text is intentional and
# safe here: every label below is a distinct, case-sensitive phrase (e.g.
# "Images:" vs "Registered images:" differ by case on the leading
# letter), so there is no risk of one pattern matching another metric's
# line.
_METRIC_PATTERNS: dict[str, re.Pattern] = {
    "rigs": re.compile(r"Rigs:\s*([0-9.]+)"),
    "cameras": re.compile(r"Cameras:\s*([0-9.]+)"),
    "frames": re.compile(r"Frames:\s*([0-9.]+)"),
    "registeredFrames": re.compile(r"Registered frames:\s*([0-9.]+)"),
    "images": re.compile(r"Images:\s*([0-9.]+)"),
    "registeredImages": re.compile(r"Registered images:\s*([0-9.]+)"),
    "points": re.compile(r"Points:\s*([0-9.]+)"),
    "observations": re.compile(r"Observations:\s*([0-9.]+)"),
    "meanTrackLength": re.compile(r"Mean track length:\s*([0-9.]+)"),
    "meanObservationsPerImage": re.compile(
        r"Mean observations per image:\s*([0-9.]+)"
    ),
    "meanReprojectionError": re.compile(
        r"Mean reprojection error:\s*([0-9.]+)"
    ),
}

_INTEGER_METRICS = {
    "rigs", "cameras", "frames", "registeredFrames", "images", "registeredImages",
    "points", "observations",
}


class ColmapParseError(Exception):
    """Raised when COLMAP output or a COLMAP binary file can't be parsed
    as expected -- e.g. a metric line whose value isn't a valid number,
    or a ``cameras.bin`` file that is truncated or has an unknown model
    ID. Per the parsing rules, a malformed value is a parse error, never
    silently coerced to zero or skipped."""


def parse_version_output(text: str) -> dict:
    """Extract the COLMAP version and CUDA-build flag from ``-h``/version
    output such as::

        COLMAP 4.2.0 (Commit be5e291 on 2026-08-31 with CUDA)
    """
    version_match = _VERSION_PATTERN.search(text or "")
    return {
        "version": version_match.group(1) if version_match else "",
        "cuda_build": bool(_CUDA_PATTERN.search(text or "")),
    }


def parse_model_analyzer_output(text: str) -> dict:
    """Extract reconstruction metrics from ``model_analyzer`` output.

    Missing lines are simply absent from the returned dict rather than
    defaulted to zero, so callers can tell "not reported" apart from
    "reported as zero". ``totalImages`` is aliased from the ``images``
    line (COLMAP's own naming) for readability elsewhere in the app.

    A line that *is* present but whose value isn't a valid number (e.g.
    a truncated or corrupted number) raises ``ColmapParseError`` rather
    than being silently dropped or coerced to zero.
    """
    metrics: dict = {}
    for key, pattern in _METRIC_PATTERNS.items():
        match = pattern.search(text or "")
        if match is None:
            continue
        raw_value = match.group(1)
        try:
            metrics[key] = int(raw_value) if key in _INTEGER_METRICS else float(raw_value)
        except ValueError as exc:
            raise ColmapParseError(
                f"Malformed value for metric '{key}': {raw_value!r}"
            ) from exc

    if "images" in metrics:
        metrics["totalImages"] = metrics["images"]

    return metrics


def calculate_registration_percentage(registered_images: int, total_images: int) -> float:
    """Percentage of images successfully registered. Returns 0.0 for an
    empty dataset rather than raising."""
    if total_images <= 0:
        return 0.0
    return (registered_images / total_images) * 100.0


# ---------------------------------------------------------------------------
# cameras.bin (COLMAP binary camera model file)
# ---------------------------------------------------------------------------

# COLMAP's stable camera model ID -> (name, param count, has distortion).
# Mirrors colmap/src/colmap/base/camera_models.h. Models with radial,
# tangential, fisheye, or FOV parameters are considered distorted; plain
# pinhole models are not.
_CAMERA_MODELS: dict[int, tuple[str, int, bool]] = {
    0: ("SIMPLE_PINHOLE", 3, False),
    1: ("PINHOLE", 4, False),
    2: ("SIMPLE_RADIAL", 4, True),
    3: ("RADIAL", 5, True),
    4: ("OPENCV", 8, True),
    5: ("OPENCV_FISHEYE", 8, True),
    6: ("FULL_OPENCV", 12, True),
    7: ("FOV", 5, True),
    8: ("SIMPLE_RADIAL_FISHEYE", 4, True),
    9: ("RADIAL_FISHEYE", 5, True),
    10: ("THIN_PRISM_FISHEYE", 12, True),
}


@dataclass
class CameraModelInfo:
    camera_id: int
    model_id: int
    model_name: str
    width: int
    height: int
    num_params: int
    has_distortion: bool


def parse_cameras_bin(path: Path) -> list[CameraModelInfo]:
    """Read a COLMAP ``cameras.bin`` file and return one
    ``CameraModelInfo`` per camera.

    Layout (little-endian, matches COLMAP's own ``read_write_model.py``):
    ``num_cameras: uint64``, then per camera ``camera_id: int32``,
    ``model_id: int32``, ``width: uint64``, ``height: uint64``,
    ``params: num_params * float64``.

    Raises ``ColmapParseError`` if the file is truncated or references an
    unknown camera model ID -- never silently skipped or guessed.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ColmapParseError(f"Could not read cameras.bin: {exc}") from exc

    if len(data) < 8:
        raise ColmapParseError(f"cameras.bin is truncated (too short): {path}")

    offset = 0
    (num_cameras,) = struct.unpack_from("<Q", data, offset)
    offset += 8

    cameras: list[CameraModelInfo] = []
    for _ in range(num_cameras):
        header_size = 4 + 4 + 8 + 8
        if offset + header_size > len(data):
            raise ColmapParseError(f"cameras.bin is truncated while reading a camera header: {path}")
        camera_id, model_id, width, height = struct.unpack_from("<iiQQ", data, offset)
        offset += header_size

        model = _CAMERA_MODELS.get(model_id)
        if model is None:
            raise ColmapParseError(f"Unknown COLMAP camera model ID {model_id} in {path}")
        model_name, num_params, has_distortion = model

        params_size = num_params * 8
        if offset + params_size > len(data):
            raise ColmapParseError(
                f"cameras.bin is truncated while reading params for camera {camera_id}: {path}"
            )
        offset += params_size  # parameter values themselves aren't needed for QC

        cameras.append(
            CameraModelInfo(
                camera_id=camera_id,
                model_id=model_id,
                model_name=model_name,
                width=width,
                height=height,
                num_params=num_params,
                has_distortion=has_distortion,
            )
        )

    return cameras

