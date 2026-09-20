"""``ReconstructionQC``: validates a COLMAP reconstruction using real
filesystem evidence and already-parsed reconstruction metrics before the
project is allowed to proceed to LichtFeld.

Ownership chain (per the specification): ``COLMAPManager`` builds/runs
COLMAP commands and persists what ``model_analyzer`` reported;
``ReconstructionState`` derives a coarse pipeline stage from disk
evidence; this module sits on top of both and produces a QC verdict
(``NOT_READY`` / ``FAILED`` / ``WARNING`` / ``READY``) plus the specific
warnings/errors that led to it. The GUI only ever asks this class for a
``QCResult`` -- no QC arithmetic lives in ``reconstruction_qc_panel.py``.

QC never re-runs COLMAP. It reads:
* the files already on disk (database, image junction, sparse model
  binaries) through ``COLMAPManager``'s existing path resolution, and
* the metrics ``COLMAPManager`` already parsed and persisted into
  ``project.json``'s ``colmap.analysis`` section after a successful
  ``model_analyzer`` run (Phase 04).

Camera model / distortion detection is new in this phase: it reads
``cameras.bin`` directly (via ``colmap_parser.parse_cameras_bin``) since
``model_analyzer``'s text output never names camera models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.colmap_manager import COLMAPManager
from src.core.logger import get_named_logger
from src.core.project_manager import ProjectLoadError, ProjectManager
from src.core.reconstruction_state import STATE_NOT_STARTED, derive_reconstruction_state
from src.utils.colmap_parser import (
    ColmapParseError,
    calculate_registration_percentage,
    parse_cameras_bin,
)

QC_STATE_NOT_READY = "NOT_READY"
QC_STATE_FAILED = "FAILED"
QC_STATE_WARNING = "WARNING"
QC_STATE_READY = "READY"

# Reprojection-error / track-length thresholds are warning-only defaults,
# never automatic-failure conditions, per the specification's
# "must not be used to falsely label a reconstruction as failed unless
# explicitly configured" rule. They're constructor parameters so a
# caller can tune them without touching this module.
DEFAULT_REPROJECTION_WARNING_PX = 1.0
DEFAULT_REPROJECTION_CRITICAL_PX = 2.0
DEFAULT_MIN_TRACK_LENGTH = 3.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class QCResult:
    total_images: int = 0
    registered_images: int = 0
    registration_percentage: float = 0.0

    cameras: int = 0
    registered_cameras: int = 0
    frames: int = 0
    registered_frames: int = 0

    points: int = 0
    observations: int = 0
    mean_track_length: Optional[float] = None
    mean_observations_per_image: Optional[float] = None
    mean_reprojection_error_px: Optional[float] = None

    camera_models: list[str] = field(default_factory=list)
    distorted_camera_models: list[str] = field(default_factory=list)

    required_files_present: bool = False
    database_valid: bool = False
    junction_valid: bool = False

    state: str = QC_STATE_NOT_READY
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    checked_at: str = ""

    @property
    def is_ready_for_lichtfeld(self) -> bool:
        """The gate the future 'Send to LichtFeld' action (Phase 06) will
        use -- READY or WARNING both produce a usable reconstruction;
        only FAILED/NOT_READY block it."""
        return self.state in (QC_STATE_READY, QC_STATE_WARNING)

    def to_project_json_dict(self) -> dict[str, Any]:
        """Shape matching project.json's ``reconstructionQC`` section."""
        return {
            "lastCheckedAt": self.checked_at,
            "state": self.state,
            "totalImages": self.total_images,
            "registeredImages": self.registered_images,
            "registrationPercentage": self.registration_percentage,
            "cameras": self.cameras,
            "registeredCameras": self.registered_cameras,
            "frames": self.frames,
            "registeredFrames": self.registered_frames,
            "points": self.points,
            "observations": self.observations,
            "meanTrackLength": self.mean_track_length,
            "meanObservationsPerImage": self.mean_observations_per_image,
            "meanReprojectionErrorPx": self.mean_reprojection_error_px,
            "cameraModels": self.camera_models,
            "distortedCameraModels": self.distorted_camera_models,
            "requiredFilesPresent": self.required_files_present,
            "databaseValid": self.database_valid,
            "junctionValid": self.junction_valid,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class ReconstructionQC:
    """Responsibilities (per spec): run, validate_required_files,
    collect_metrics, calculate_registration_percentage,
    detect_camera_models, detect_distortion, evaluate_state."""

    def __init__(
        self,
        project_manager: ProjectManager,
        colmap_manager: Optional[COLMAPManager] = None,
        reprojection_warning_px: float = DEFAULT_REPROJECTION_WARNING_PX,
        reprojection_critical_px: float = DEFAULT_REPROJECTION_CRITICAL_PX,
        min_track_length: float = DEFAULT_MIN_TRACK_LENGTH,
    ) -> None:
        self.project_manager = project_manager
        self.colmap_manager = colmap_manager or COLMAPManager(project_manager)
        self.reprojection_warning_px = reprojection_warning_px
        self.reprojection_critical_px = reprojection_critical_px
        self.min_track_length = min_track_length
        self.logger = get_named_logger("reconstruction_qc")

    def _current(self):
        if self.project_manager.current is None:
            raise ProjectLoadError("No project is currently open.")
        return self.project_manager.current

    # -- file evidence --------------------------------------------------------

    def validate_required_files(self) -> dict[str, Any]:
        """Check database, image junction, sparse directory, and the
        three required sparse-model binaries. Never modifies anything."""
        database_path = self.colmap_manager.database_path()
        sparse_model_path = self.colmap_manager.sparse_model_path()
        junction_path = self.colmap_manager.images_junction_path()
        source_images_path = self.colmap_manager.active_image_source_path()

        database_valid = database_path.exists() and database_path.stat().st_size > 0

        sparse_dir_exists = sparse_model_path.is_dir()
        file_status: dict[str, bool] = {}
        for name in ("cameras.bin", "images.bin", "points3D.bin"):
            file_path = sparse_model_path / name
            file_status[name] = file_path.exists() and file_path.stat().st_size > 0
        required_files_present = sparse_dir_exists and all(file_status.values())

        junction_valid = False
        if junction_path.exists() or junction_path.is_symlink():
            try:
                junction_valid = junction_path.resolve() == source_images_path.resolve()
            except OSError:
                junction_valid = False

        result = {
            "database_valid": database_valid,
            "sparse_dir_exists": sparse_dir_exists,
            "file_status": file_status,
            "required_files_present": required_files_present,
            "junction_valid": junction_valid,
        }
        self.logger.info("Required file validation result: %s", result)
        return result

    # -- metrics ----------------------------------------------------------------

    def collect_metrics(self) -> dict[str, Any]:
        """Return the metrics ``COLMAPManager`` already parsed from
        ``model_analyzer`` and persisted after Phase 04's pipeline ran.
        QC never re-runs COLMAP to obtain these -- an empty dict means
        no analysis has completed yet, never a fabricated zero."""
        current = self._current()
        analysis = current.data.colmap_info.get("analysis", {}) or {}
        metrics = dict(analysis) if analysis.get("completed") else {}
        self.logger.info("Metrics parsed: %s", metrics or "(none available)")
        return metrics

    def calculate_registration_percentage(self, registered_images: int, total_images: int) -> float:
        return calculate_registration_percentage(registered_images, total_images)

    # -- camera models / distortion ----------------------------------------------

    def detect_camera_models(self) -> list:
        """Read cameras.bin directly and return the parsed
        ``CameraModelInfo`` list. Returns [] (not an error) if the file
        doesn't exist yet -- callers combine this with the required-file
        evidence to decide overall QC state."""
        cameras_bin = self.colmap_manager.sparse_model_path() / "cameras.bin"
        if not cameras_bin.exists() or cameras_bin.stat().st_size == 0:
            return []
        try:
            cameras = parse_cameras_bin(cameras_bin)
        except ColmapParseError as exc:
            self.logger.error("Camera model detection failed: %s", exc)
            return []
        model_names = sorted({c.model_name for c in cameras})
        self.logger.info("Camera model detection result: %s", model_names)
        return cameras

    def detect_distortion(self, cameras: list) -> list[str]:
        distorted = sorted({c.model_name for c in cameras if c.has_distortion})
        self.logger.info("Distortion detection result: %s", distorted or "(none)")
        return distorted

    # -- state evaluation -------------------------------------------------------

    def evaluate_state(self, result: QCResult) -> tuple[str, list[str], list[str]]:
        """Decide READY / WARNING / FAILED from already-populated
        ``result`` fields. Does not touch the filesystem.

        Camera distortion is always reported in ``warnings`` for
        visibility, but per the specification's reference baseline (a
        fully-registered, low-error SIMPLE_RADIAL reconstruction is
        expected to reach READY, not WARNING) it never by itself
        downgrades the state -- distortion is a downstream LichtFeld
        training consideration, not evidence the reconstruction itself
        needs attention. Only genuine quality issues (partial
        registration, high reprojection error, short track length)
        trigger WARNING.
        """
        warnings: list[str] = []
        errors: list[str] = []
        quality_issue_found = False

        if not result.database_valid:
            errors.append("COLMAP database is missing or empty.")
        if not result.required_files_present:
            errors.append(
                "Required sparse model files (cameras.bin, images.bin, points3D.bin) "
                "are missing or empty."
            )
        if not result.junction_valid:
            errors.append(
                "Image junction is missing or does not resolve to the active image directory."
            )
        if errors:
            return QC_STATE_FAILED, warnings, errors

        if result.registered_images == 0:
            errors.append("No images were registered.")
            return QC_STATE_FAILED, warnings, errors

        if result.points <= 0:
            errors.append("Sparse reconstruction contains zero points.")
            return QC_STATE_FAILED, warnings, errors

        if result.registered_images < result.total_images:
            warnings.append(
                f"Only {result.registered_images} of {result.total_images} images were "
                f"registered ({result.registration_percentage:.1f}%)."
            )
            quality_issue_found = True

        if result.mean_reprojection_error_px is None:
            warnings.append("Mean reprojection error is not available.")
            quality_issue_found = True
        elif result.mean_reprojection_error_px > self.reprojection_critical_px:
            warnings.append(
                f"Mean reprojection error is high: "
                f"{result.mean_reprojection_error_px:.3f}px "
                f"(> {self.reprojection_critical_px}px)."
            )
            quality_issue_found = True
        elif result.mean_reprojection_error_px > self.reprojection_warning_px:
            warnings.append(
                f"Mean reprojection error is above the normal reference: "
                f"{result.mean_reprojection_error_px:.3f}px "
                f"(> {self.reprojection_warning_px}px)."
            )
            quality_issue_found = True

        if result.mean_track_length is not None and result.mean_track_length < self.min_track_length:
            warnings.append(
                f"Mean track length is short: {result.mean_track_length:.3f} "
                f"(< {self.min_track_length})."
            )
            quality_issue_found = True

        if result.distorted_camera_models:
            # Informational only -- reported, but does not set
            # quality_issue_found, so it never turns READY into WARNING.
            warnings.append(
                "Distorted camera model detected: "
                + ", ".join(result.distorted_camera_models)
                + ". LichtFeld may require undistortion (--undistort/--gut) before training."
            )

        state = QC_STATE_WARNING if quality_issue_found else QC_STATE_READY
        return state, warnings, errors

    # -- orchestration ------------------------------------------------------------

    def run(self) -> QCResult:
        """Run the complete QC pass for the active project and persist
        the result into project.json's ``reconstructionQC`` section."""
        self.logger.info("Reconstruction QC started")
        current = self._current()

        # Nothing has ever been attempted (no database, no sparse
        # reconstruction) -- NOT_READY, not FAILED: there is no broken
        # evidence to report, only an absence of any attempt so far.
        reconstruction_state = derive_reconstruction_state(
            self.colmap_manager.database_path(),
            self.colmap_manager.sparse_model_path(),
            current.data.colmap_info,
        )
        if reconstruction_state.state == STATE_NOT_STARTED:
            result = QCResult(state=QC_STATE_NOT_READY, checked_at=_now_iso())
            self.logger.info("Reconstruction QC completed: state=%s (nothing run yet)", result.state)
            self._persist(result)
            return result

        file_evidence = self.validate_required_files()
        metrics = self.collect_metrics()
        cameras = self.detect_camera_models()
        camera_models = sorted({c.model_name for c in cameras})
        distorted = self.detect_distortion(cameras)

        total_images = metrics.get("totalImages", 0)
        registered_images = metrics.get("registeredImages", 0)

        result = QCResult(
            total_images=total_images,
            registered_images=registered_images,
            registration_percentage=self.calculate_registration_percentage(
                registered_images, total_images
            ),
            cameras=metrics.get("cameras", len(cameras)),
            registered_cameras=registered_images,
            frames=total_images,
            registered_frames=registered_images,
            points=metrics.get("points", 0),
            observations=metrics.get("observations", 0),
            mean_track_length=metrics.get("meanTrackLength"),
            mean_observations_per_image=metrics.get("meanObservationsPerImage"),
            mean_reprojection_error_px=metrics.get("meanReprojectionError"),
            camera_models=camera_models,
            distorted_camera_models=distorted,
            required_files_present=file_evidence["required_files_present"],
            database_valid=file_evidence["database_valid"],
            junction_valid=file_evidence["junction_valid"],
            checked_at=_now_iso(),
        )

        state, warnings, errors = self.evaluate_state(result)
        result.state = state
        result.warnings = warnings
        result.errors = errors

        self.logger.info("QC state calculated: %s", state)
        if errors:
            self.logger.error("Reconstruction QC failure: %s", errors)
        self._persist(result)
        self.logger.info("Reconstruction QC completed")
        return result

    def _persist(self, result: QCResult) -> None:
        current = self._current()
        current.data.reconstruction_qc_info = result.to_project_json_dict()
        self.project_manager.save_project_json()
        self.logger.info("project.json QC update: state=%s", result.state)
