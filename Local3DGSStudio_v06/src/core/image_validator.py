"""``ImageValidator``: validates an input image dataset before COLMAP
processing.

This module is pure Python (no Qt dependency) so it can be unit tested
directly; the GUI-facing non-blocking wrapper lives in
``ImageValidationWorker`` at the bottom of this file, which runs the same
logic on a ``QThread`` and reports progress via signals.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QThread, Signal

from src.utils.hash_utils import calculate_sha256
from src.utils.image_utils import inspect_image, is_supported_image
from src.utils.filesystem import human_readable_size

MINIMUM_RESOLUTION = (640, 480)

STATUS_VALID = "VALID"
STATUS_WARNING = "WARNING"
STATUS_INVALID = "INVALID"


@dataclass
class ImageValidationRecord:
    filename: str
    absolute_path: Path
    status: str = STATUS_VALID
    extension: str = ""
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    sha256: str = ""
    issues: list[str] = field(default_factory=list)

    @property
    def issue_summary(self) -> str:
        return "; ".join(self.issues) if self.issues else ""


@dataclass
class ValidationSummary:
    total_images: int = 0
    valid_images: int = 0
    warning_images: int = 0
    invalid_images: int = 0
    duplicate_images: int = 0
    total_size_bytes: int = 0
    min_width: int = 0
    max_width: int = 0
    min_height: int = 0
    max_height: int = 0
    most_common_width: int = 0
    most_common_height: int = 0
    overall_status: str = STATUS_VALID

    @property
    def total_size_human(self) -> str:
        return human_readable_size(self.total_size_bytes)

    @property
    def common_resolution(self) -> str:
        if self.most_common_width and self.most_common_height:
            return f"{self.most_common_width}x{self.most_common_height}"
        return "n/a"


ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]


class ImageValidator:
    """Runs every validation stage over a directory of images.

    Responsibilities (per spec): validate_file, validate_directory,
    calculate_sha256, validate_resolution, validate_file_size,
    detect_duplicates.
    """

    def validate_file_size(self, path: Path) -> tuple[int, Optional[str]]:
        """Return (size_in_bytes, issue_or_None). A zero-byte file is a
        critical (INVALID) issue."""
        size = path.stat().st_size
        if size == 0:
            return size, "Zero-byte file"
        return size, None

    def validate_resolution(self, width: int, height: int) -> Optional[str]:
        """Return a warning string if below the minimum resolution
        threshold, or None. This is a warning, never an automatic
        rejection, per the specification."""
        min_w, min_h = MINIMUM_RESOLUTION
        if width < min_w or height < min_h:
            return f"Below minimum recommended resolution ({min_w}x{min_h})"
        return None

    def validate_file(self, path: Path) -> ImageValidationRecord:
        """Run every per-file check (format, existence, readability,
        corruption, resolution, file size) on a single image."""
        record = ImageValidationRecord(
            filename=path.name,
            absolute_path=path,
            extension=path.suffix.lower(),
        )

        if not path.exists():
            record.status = STATUS_INVALID
            record.issues.append("File does not exist")
            return record

        if not is_supported_image(path):
            record.status = STATUS_INVALID
            record.issues.append(f"Unsupported format: {path.suffix}")
            return record

        size, size_issue = self.validate_file_size(path)
        record.file_size_bytes = size
        if size_issue:
            record.status = STATUS_INVALID
            record.issues.append(size_issue)
            return record

        inspection = inspect_image(path)
        if not inspection.readable or inspection.corrupt:
            record.status = STATUS_INVALID
            record.issues.append(f"Corrupt or unreadable image: {inspection.error}")
            return record

        record.width = inspection.width
        record.height = inspection.height

        resolution_issue = self.validate_resolution(inspection.width, inspection.height)
        if resolution_issue:
            record.status = STATUS_WARNING
            record.issues.append(resolution_issue)

        try:
            record.sha256 = calculate_sha256(path)
        except OSError as exc:
            record.status = STATUS_INVALID
            record.issues.append(f"Could not read file for hashing: {exc}")

        return record

    def detect_duplicates(
        self, records: list[ImageValidationRecord]
    ) -> tuple[set[str], set[str]]:
        """Return (duplicate_filenames_lower, duplicate_sha256_hashes)
        found among already-validated records. Never deletes anything --
        the caller only reports these."""
        filename_counts = Counter(r.filename.lower() for r in records)
        duplicate_filenames = {name for name, count in filename_counts.items() if count > 1}

        hash_counts = Counter(r.sha256 for r in records if r.sha256)
        duplicate_hashes = {h for h, count in hash_counts.items() if count > 1}

        return duplicate_filenames, duplicate_hashes

    def validate_directory(
        self,
        directory: Path,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
    ) -> tuple[list[ImageValidationRecord], ValidationSummary]:
        """Validate every supported image file in ``directory``.

        ``progress_callback(current, total, filename)`` is invoked after
        each file. ``cancel_check()`` is polled between files and, if it
        returns True, validation stops early (already-processed records
        are still returned).
        """
        if not directory.is_dir():
            return [], ValidationSummary(overall_status=STATUS_INVALID)

        files = sorted(
            (p for p in directory.iterdir() if p.is_file() and is_supported_image(p)),
            key=lambda p: p.name.lower(),
        )
        total = len(files)
        records: list[ImageValidationRecord] = []

        for index, path in enumerate(files, start=1):
            if cancel_check is not None and cancel_check():
                break
            record = self.validate_file(path)
            records.append(record)
            if progress_callback is not None:
                progress_callback(index, total, path.name)

        duplicate_filenames, duplicate_hashes = self.detect_duplicates(records)
        for record in records:
            is_dup = record.filename.lower() in duplicate_filenames or (
                record.sha256 and record.sha256 in duplicate_hashes
            )
            if is_dup and record.status == STATUS_VALID:
                record.status = STATUS_WARNING
            if is_dup:
                record.issues.append("Duplicate detected")

        summary = self._build_summary(records, duplicate_filenames, duplicate_hashes)
        return records, summary

    def _build_summary(
        self,
        records: list[ImageValidationRecord],
        duplicate_filenames: set[str],
        duplicate_hashes: set[str],
    ) -> ValidationSummary:
        summary = ValidationSummary(total_images=len(records))
        if not records:
            summary.overall_status = STATUS_WARNING
            return summary

        widths = [r.width for r in records if r.width]
        heights = [r.height for r in records if r.height]

        for record in records:
            summary.total_size_bytes += record.file_size_bytes
            if record.status == STATUS_VALID:
                summary.valid_images += 1
            elif record.status == STATUS_WARNING:
                summary.warning_images += 1
            else:
                summary.invalid_images += 1

        # Count each duplicate-content group once (not once per member).
        summary.duplicate_images = sum(
            1 for r in records if r.filename.lower() in duplicate_filenames
        ) if duplicate_filenames else 0
        if duplicate_hashes:
            summary.duplicate_images = max(
                summary.duplicate_images,
                sum(1 for r in records if r.sha256 in duplicate_hashes),
            )

        if widths:
            summary.min_width = min(widths)
            summary.max_width = max(widths)
            summary.most_common_width = Counter(widths).most_common(1)[0][0]
        if heights:
            summary.min_height = min(heights)
            summary.max_height = max(heights)
            summary.most_common_height = Counter(heights).most_common(1)[0][0]

        if summary.invalid_images > 0:
            summary.overall_status = STATUS_INVALID
        elif summary.warning_images > 0 or summary.duplicate_images > 0:
            summary.overall_status = STATUS_WARNING
        else:
            summary.overall_status = STATUS_VALID

        return summary


class ImageValidationWorker(QThread):
    """Runs ``ImageValidator.validate_directory`` off the GUI thread.

    Signals:
        progress(current, total, filename)
        finished_result(records, summary)
        failed(error_message)
    """

    progress = Signal(int, int, str)
    finished_result = Signal(list, object)
    failed = Signal(str)

    def __init__(self, directory: Path, parent=None) -> None:
        super().__init__(parent)
        self.directory = directory
        self.validator = ImageValidator()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # noqa: D102 - QThread override
        try:
            records, summary = self.validator.validate_directory(
                self.directory,
                progress_callback=lambda cur, total, name: self.progress.emit(cur, total, name),
                cancel_check=lambda: self._cancelled,
            )
            self.finished_result.emit(records, summary)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the GUI
            self.failed.emit(str(exc))
