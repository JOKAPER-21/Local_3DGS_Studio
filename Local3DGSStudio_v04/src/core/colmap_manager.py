"""``COLMAPManager``: the single facade for everything COLMAP-related.

Mirrors the role ``ProjectManager`` / ``InputManager`` play for their own
areas: the GUI never builds a COLMAP command or a project-relative path
itself -- it asks this class for a ready-to-run ``ColmapCommand`` and
reports the result back so project.json can be updated.

Command execution itself is left to the caller (the GUI, via the
existing ``ManagedProcess`` / ``QProcess`` wrapper) so this module stays
free of any Qt event-loop dependency and is fully unit-testable.
"""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.core.colmap_config import COLMAPConfig
from src.core.project_manager import ProjectLoadError, ProjectManager
from src.core.reconstruction_state import (
    ReconstructionState,
    derive_reconstruction_state,
    sparse_model_files_exist,
)
from src.utils.colmap_parser import parse_version_output
from src.utils.image_utils import is_supported_image
from src.utils.windows_junction import JunctionResult, ensure_image_junction

SUBCOMMAND_DATABASE_CREATOR = "database_creator"
SUBCOMMAND_FEATURE_EXTRACTOR = "feature_extractor"
SUBCOMMAND_EXHAUSTIVE_MATCHER = "exhaustive_matcher"
SUBCOMMAND_MAPPER = "mapper"
SUBCOMMAND_MODEL_ANALYZER = "model_analyzer"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DatabaseExistsError(Exception):
    """Raised when creating a database would silently overwrite one."""


class SparseModelExistsError(Exception):
    """Raised when running the mapper would silently overwrite an
    existing sparse reconstruction."""


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


@dataclass
class ColmapDetectionResult:
    detected: bool
    path: str = ""
    version: str = ""
    cuda_build: bool = False
    raw_output: str = ""
    error: str = ""


def build_colmap_invocation(colmap_path: str, args: list[str]) -> tuple[str, list[str]]:
    """Wrap ``.bat``/``.cmd`` executables with ``cmd.exe /c`` on Windows so
    ``QProcess`` (and ``subprocess``) can launch them directly. Anything
    else (a real ``.exe`` on Windows, or a plain executable elsewhere) is
    launched as-is."""
    suffix = Path(colmap_path).suffix.lower()
    if suffix in (".bat", ".cmd") and platform.system() == "Windows":
        return "cmd.exe", ["/c", str(colmap_path), *args]
    return str(colmap_path), list(args)


def detect_colmap_executable(path: str, timeout: float = 8.0) -> ColmapDetectionResult:
    """Verify the configured COLMAP path exists and run a harmless
    ``-h`` to confirm it actually is COLMAP and extract its version.

    This is a short (sub-second, timeout-bounded), one-shot check --
    unlike the pipeline stages, it is safe to run synchronously from a
    button click rather than through ``ManagedProcess``.
    """
    if not path:
        return ColmapDetectionResult(detected=False, error="No COLMAP path configured.")

    exe_path = Path(path)
    if not exe_path.is_file():
        return ColmapDetectionResult(
            detected=False, path=path, error=f"COLMAP executable not found: {path}"
        )

    executable, arguments = build_colmap_invocation(path, ["-h"])
    try:
        completed = subprocess.run(
            [executable, *arguments], capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ColmapDetectionResult(detected=False, path=path, error=f"Failed to run COLMAP: {exc}")

    combined_output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    parsed = parse_version_output(combined_output)

    if not parsed["version"]:
        return ColmapDetectionResult(
            detected=False,
            path=path,
            raw_output=combined_output,
            error="COLMAP ran, but its version could not be determined from the output.",
        )

    return ColmapDetectionResult(
        detected=True,
        path=path,
        version=parsed["version"],
        cuda_build=parsed["cuda_build"],
        raw_output=combined_output,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass
class ColmapCommand:
    """A fully-resolved, ready-to-run COLMAP invocation."""

    step: str
    subcommand: str
    colmap_args: list[str]
    executable: str
    process_arguments: list[str]
    display_command: str


def build_database_creator_args(database_path: Path) -> list[str]:
    return ["--database_path", str(database_path)]


def build_feature_extractor_args(
    database_path: Path, image_path: Path, use_gpu: bool, threads: int
) -> list[str]:
    return [
        "--FeatureExtraction.use_gpu", "1" if use_gpu else "0",
        "--FeatureExtraction.num_threads", str(threads),
        "--database_path", str(database_path),
        "--image_path", str(image_path),
    ]


def build_exhaustive_matcher_args(database_path: Path, use_gpu: bool) -> list[str]:
    return [
        "--FeatureMatching.use_gpu", "1" if use_gpu else "0",
        "--database_path", str(database_path),
    ]


def build_mapper_args(database_path: Path, image_path: Path, output_path: Path) -> list[str]:
    return [
        "--database_path", str(database_path),
        "--image_path", str(image_path),
        "--output_path", str(output_path),
    ]


def build_model_analyzer_args(model_path: Path) -> list[str]:
    return ["--path", str(model_path)]


def _make_command(step: str, colmap_path: str, subcommand: str, args: list[str]) -> ColmapCommand:
    colmap_args = [subcommand, *args]
    executable, process_arguments = build_colmap_invocation(colmap_path, colmap_args)
    display = " ".join([colmap_path, *colmap_args])
    return ColmapCommand(
        step=step,
        subcommand=subcommand,
        colmap_args=colmap_args,
        executable=executable,
        process_arguments=process_arguments,
        display_command=display,
    )


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


@dataclass
class PreflightCheckResult:
    name: str
    passed: bool
    message: str


@dataclass
class PreflightReport:
    checks: list[PreflightCheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> list[PreflightCheckResult]:
        return [check for check in self.checks if not check.passed]


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class COLMAPManager:
    """Responsibilities (per spec): detectCOLMAP, getVersion,
    createDatabase, extractFeatures, matchFeatures, runMapper,
    analyzeModel, getReconstructionState."""

    def __init__(
        self, project_manager: ProjectManager, config: Optional[COLMAPConfig] = None
    ) -> None:
        self.project_manager = project_manager
        self.config = config or COLMAPConfig()

    def _require_current(self):
        if self.project_manager.current is None:
            raise ProjectLoadError("No project is currently open.")
        return self.project_manager.current

    # -- path resolution (always through ProjectPathResolver) ---------------

    def database_path(self) -> Path:
        return self._require_current().resolver.colmap / "database.db"

    def sparse_root_path(self) -> Path:
        return self._require_current().resolver.colmap / "sparse"

    def sparse_model_path(self) -> Path:
        return self.sparse_root_path() / "0"

    def images_junction_path(self) -> Path:
        return self._require_current().resolver.colmap / "images"

    def active_image_source_path(self) -> Path:
        return self._require_current().resolver.images

    # -- existence checks -----------------------------------------------------

    def database_exists(self) -> bool:
        path = self.database_path()
        return path.exists() and path.stat().st_size > 0

    def sparse_model_exists(self) -> bool:
        return sparse_model_files_exist(self.sparse_model_path())

    # -- image junction ---------------------------------------------------------

    def ensure_image_junction(self) -> JunctionResult:
        return ensure_image_junction(self.active_image_source_path(), self.images_junction_path())

    # -- input validation gate ---------------------------------------------------

    def check_input_validation_gate(self) -> tuple[bool, bool, str]:
        """Returns ``(allowed, requires_confirmation, message)`` per the
        specification's input-validation gate: INVALID blocks outright;
        WARNING (or never-validated) allows but asks for confirmation;
        VALID allows silently."""
        current = self._require_current()
        status = current.data.validation_info.get("validationStatus", "notValidated")
        if status == "INVALID":
            return False, False, "Resolve invalid image validation errors before running COLMAP."
        if status == "VALID":
            return True, False, "Image validation passed."
        if status == "WARNING":
            return True, True, "Image validation reported warnings. Continue anyway?"
        return True, True, "Images have not been validated yet. Continue anyway?"

    # -- preflight -----------------------------------------------------------------

    def run_preflight(self, detection: ColmapDetectionResult) -> PreflightReport:
        report = PreflightReport()

        def add(name: str, passed: bool, message: str) -> None:
            report.checks.append(PreflightCheckResult(name, passed, message))

        current = self.project_manager.current
        add("Project loaded", current is not None,
            "Open or create a project first." if current is None else "Project is open.")
        if current is None:
            return report

        add("project.json valid", True, "project.json loaded successfully.")

        image_dir = current.resolver.images
        add("Active image directory exists", image_dir.is_dir(), str(image_dir))

        image_count = 0
        if image_dir.is_dir():
            image_count = sum(1 for p in image_dir.iterdir() if p.is_file() and is_supported_image(p))
        add("Image count greater than zero", image_count > 0, f"{image_count} image(s) found.")

        validation_status = current.data.validation_info.get("validationStatus", "notValidated")
        add(
            "Input validation available",
            validation_status != "notValidated",
            f"Validation status: {validation_status}",
        )

        add("COLMAP configured", bool(self.config.executable_path),
            self.config.executable_path or "No COLMAP path configured.")

        colmap_exists = bool(self.config.executable_path) and Path(self.config.executable_path).is_file()
        add("COLMAP executable exists", colmap_exists,
            self.config.executable_path if colmap_exists else "Configured COLMAP path not found.")

        add("COLMAP version detected", detection.detected,
            detection.version if detection.detected else detection.error)

        compatible = detection.detected and detection.version.startswith("4.")
        add("COLMAP version compatible", compatible,
            f"Detected version {detection.version}" if detection.detected else "Version not detected.")

        add("Database path available", True, str(self.database_path()))
        add("Sparse output path available", True, str(self.sparse_root_path()))

        return report

    # -- command builders ---------------------------------------------------------

    def build_database_creation_command(self) -> ColmapCommand:
        args = build_database_creator_args(self.database_path())
        return _make_command("Database", self.config.executable_path, SUBCOMMAND_DATABASE_CREATOR, args)

    def build_feature_extraction_command(self) -> ColmapCommand:
        args = build_feature_extractor_args(
            self.database_path(),
            self.images_junction_path(),
            self.config.feature_extraction_use_gpu,
            self.config.feature_extraction_threads,
        )
        return _make_command("Features", self.config.executable_path, SUBCOMMAND_FEATURE_EXTRACTOR, args)

    def build_feature_matching_command(self) -> ColmapCommand:
        args = build_exhaustive_matcher_args(self.database_path(), self.config.feature_matching_use_gpu)
        return _make_command("Matching", self.config.executable_path, SUBCOMMAND_EXHAUSTIVE_MATCHER, args)

    def build_mapper_command(self) -> ColmapCommand:
        args = build_mapper_args(
            self.database_path(), self.images_junction_path(), self.sparse_root_path()
        )
        return _make_command("Mapper", self.config.executable_path, SUBCOMMAND_MAPPER, args)

    def build_model_analyzer_command(self) -> ColmapCommand:
        args = build_model_analyzer_args(self.sparse_model_path())
        return _make_command("Analysis", self.config.executable_path, SUBCOMMAND_MODEL_ANALYZER, args)

    # -- safety-guarded step preparation --------------------------------------------

    def create_database(self, force: bool = False) -> ColmapCommand:
        """Prepare the database-creation step. Raises
        ``DatabaseExistsError`` unless ``force=True`` is passed after the
        user has explicitly confirmed replacing it -- only the database
        file itself is removed, sparse reconstruction data is untouched."""
        if self.database_exists() and not force:
            raise DatabaseExistsError(f"A database already exists at: {self.database_path()}")
        if force and self.database_path().exists():
            self.database_path().unlink()
        self.database_path().parent.mkdir(parents=True, exist_ok=True)
        return self.build_database_creation_command()

    def run_mapper(self, force: bool = False) -> ColmapCommand:
        """Prepare the mapper step. Raises ``SparseModelExistsError``
        unless ``force=True`` is passed after explicit user confirmation
        -- only then is the existing ``sparse`` folder removed."""
        if self.sparse_model_exists() and not force:
            raise SparseModelExistsError(
                f"A sparse reconstruction already exists at: {self.sparse_model_path()}"
            )
        if force and self.sparse_root_path().is_dir():
            import shutil

            shutil.rmtree(self.sparse_root_path())
        self.sparse_root_path().mkdir(parents=True, exist_ok=True)
        return self.build_mapper_command()

    # -- reconstruction state -------------------------------------------------------

    def get_reconstruction_state(self) -> ReconstructionState:
        current = self._require_current()
        return derive_reconstruction_state(
            self.database_path(), self.sparse_model_path(), current.data.colmap_info
        )

    # -- project.json persistence (only through ProjectManager) ---------------------

    def record_database_created(self) -> None:
        current = self._require_current()
        current.data.colmap_info["database"] = self._relative_colmap_path("database.db")
        current.data.colmap_info["state"] = "DATABASE_CREATED"
        current.data.colmap_info["lastRun"] = _now_iso()
        self.project_manager.save_project_json()

    def record_feature_extraction_completed(self, use_gpu: bool, threads: int) -> None:
        current = self._require_current()
        current.data.colmap_info["featureExtraction"] = {
            "completed": True, "useGPU": use_gpu, "numThreads": threads,
        }
        current.data.colmap_info["state"] = "FEATURES_EXTRACTED"
        current.data.colmap_info["lastRun"] = _now_iso()
        self.project_manager.save_project_json()

    def record_feature_matching_completed(self, use_gpu: bool, method: str = "exhaustive") -> None:
        current = self._require_current()
        current.data.colmap_info["featureMatching"] = {
            "completed": True, "method": method, "useGPU": use_gpu,
        }
        current.data.colmap_info["state"] = "FEATURES_MATCHED"
        current.data.colmap_info["lastRun"] = _now_iso()
        self.project_manager.save_project_json()

    def record_mapper_completed(self) -> None:
        current = self._require_current()
        current.data.colmap_info["mapper"] = {"completed": True}
        current.data.colmap_info["sparseModel"] = self._relative_colmap_path("sparse/0")
        current.data.colmap_info["state"] = "SPARSE_RECONSTRUCTION_CREATED"
        current.data.colmap_info["lastRun"] = _now_iso()
        self.project_manager.save_project_json()

    def record_analysis_completed(self, metrics: dict) -> None:
        current = self._require_current()
        current.data.colmap_info["analysis"] = {"completed": True, **metrics}

        # Keep the flat legacy fields (read by the Dashboard) in sync.
        current.data.colmap_info["registeredImages"] = metrics.get("registeredImages", 0)
        current.data.colmap_info["sparsePoints"] = metrics.get("points", 0)
        current.data.colmap_info["observations"] = metrics.get("observations", 0)
        current.data.colmap_info["meanTrackLength"] = metrics.get("meanTrackLength", 0)
        current.data.colmap_info["meanReprojectionError"] = metrics.get("meanReprojectionError", 0)

        total = metrics.get("totalImages", 0)
        registered = metrics.get("registeredImages", 0)
        current.data.colmap_info["state"] = (
            "READY" if total > 0 and registered == total else "ANALYZED"
        )
        current.data.colmap_info["lastRun"] = _now_iso()
        self.project_manager.save_project_json()

    def _relative_colmap_path(self, suffix: str) -> str:
        current = self._require_current()
        return f"{current.data.relative_paths.colmap}/{suffix}"
