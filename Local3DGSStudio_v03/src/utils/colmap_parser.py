"""Parsing helpers for raw COLMAP CLI output.

Kept separate from ``COLMAPManager`` / the GUI so the exact regexes can be
unit tested against real captured COLMAP output without needing a COLMAP
installation or a Qt event loop.
"""

from __future__ import annotations

import re

_VERSION_PATTERN = re.compile(r"COLMAP\s+([0-9]+\.[0-9]+\.[0-9]+)")
_CUDA_PATTERN = re.compile(r"with\s+CUDA", re.IGNORECASE)

# model_analyzer prints lines like "Registered images: 293" or
# "Mean reprojection error: 0.937114px". Values may be int or float, and
# a trailing unit (e.g. "px") is tolerated but not captured.
_METRIC_PATTERNS: dict[str, re.Pattern] = {
    "cameras": re.compile(r"^\s*Cameras:\s*([0-9]+)", re.MULTILINE),
    "images": re.compile(r"^\s*Images:\s*([0-9]+)", re.MULTILINE),
    "registeredImages": re.compile(r"^\s*Registered images:\s*([0-9]+)", re.MULTILINE),
    "points": re.compile(r"^\s*Points:\s*([0-9]+)", re.MULTILINE),
    "observations": re.compile(r"^\s*Observations:\s*([0-9]+)", re.MULTILINE),
    "meanTrackLength": re.compile(r"^\s*Mean track length:\s*([0-9.]+)", re.MULTILINE),
    "meanObservationsPerImage": re.compile(
        r"^\s*Mean observations per image:\s*([0-9.]+)", re.MULTILINE
    ),
    "meanReprojectionError": re.compile(
        r"^\s*Mean reprojection error:\s*([0-9.]+)", re.MULTILINE
    ),
}

_INTEGER_METRICS = {"cameras", "images", "registeredImages", "points", "observations"}


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
    """
    metrics: dict = {}
    for key, pattern in _METRIC_PATTERNS.items():
        match = pattern.search(text or "")
        if match is None:
            continue
        value = match.group(1)
        metrics[key] = int(value) if key in _INTEGER_METRICS else float(value)

    if "images" in metrics:
        metrics["totalImages"] = metrics["images"]

    return metrics


def calculate_registration_percentage(registered_images: int, total_images: int) -> float:
    """Percentage of images successfully registered. Returns 0.0 for an
    empty dataset rather than raising."""
    if total_images <= 0:
        return 0.0
    return (registered_images / total_images) * 100.0
