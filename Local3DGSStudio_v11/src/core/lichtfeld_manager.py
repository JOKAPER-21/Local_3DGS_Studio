"""``LichtFeldManager``: the "Send to LichtFeld" orchestrator.

Ownership chain: ``ReconstructionQC`` decides whether a reconstruction is
usable at all (this manager never re-derives that -- it takes a
``QCResult`` and trusts ``is_ready_for_lichtfeld``); ``COLMAPManager``
still owns every COLMAP-related path; ``lichtfeld_staging`` owns building
the temporary, junction-based workspace LichtFeld needs. This class just
sequences those pieces and launches the executable.

Every step is logged (via the ``lichtfeld`` logger, writing to
``logs/lichtfeld.log`` like the other per-tool logs) and nothing is ever
silently swallowed -- a failure at any stage returns a
``LichtFeldLaunchResult`` with ``success=False`` and a human-readable
``error``, with the full exception logged when one occurred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QProcess

from src.core.colmap_manager import COLMAPManager
from src.core.lichtfeld_config import LichtFeldConfig
from src.core.lichtfeld_staging import StagingResult, create_staging
from src.core.logger import get_named_logger
from src.core.project_manager import ProjectLoadError, ProjectManager
from src.core.reconstruction_qc import QCResult


@dataclass
class LichtFeldLaunchResult:
    success: bool
    error: str = ""
    staging: Optional[StagingResult] = None
    pid: int = 0
    executable_path: str = ""
    command: list = field(default_factory=list)


class LichtFeldManager:
    def __init__(
        self,
        project_manager: ProjectManager,
        config: LichtFeldConfig | None = None,
    ) -> None:
        self.project_manager = project_manager
        self.config = config or LichtFeldConfig()
        self.colmap_manager = COLMAPManager(project_manager)
        self.logger = get_named_logger("lichtfeld")

    def _require_current(self):
        if self.project_manager.current is None:
            raise ProjectLoadError("No project is currently open.")
        return self.project_manager.current

    # -- validation -----------------------------------------------------------

    def validate_executable(self) -> tuple[bool, str]:
        """Returns (ok, path-or-error-message)."""
        raw_path = self.config.executable_path
        if not raw_path:
            return False, "LichtFeld executable path is not configured (see Settings)."
        path = Path(raw_path)
        if not path.is_file():
            return False, f"LichtFeld executable not found at: {raw_path}"
        return True, str(path)

    def image_source_path(self) -> Path:
        return self.colmap_manager.active_image_source_path()

    def sparse_model_path(self) -> Path:
        return self.colmap_manager.sparse_model_path()

    # -- the full "Send to LichtFeld" sequence ---------------------------------

    def send_to_lichtfeld(self, qc_result: QCResult) -> LichtFeldLaunchResult:
        current = self._require_current()
        self.logger.info(
            "Send to LichtFeld requested. project_root=%s qc_state=%s registered=%s/%s",
            current.project_root, qc_result.state, qc_result.registered_images, qc_result.total_images,
        )

        staged = self._validate_and_stage(qc_result)
        if not staged.success:
            return staged
        staging = staged.staging
        executable_path = staged.executable_path

        # NOTE: LichtFeld Studio's command-line contract for auto-loading a
        # COLMAP dataset has not been documented to this application, so we
        # deliberately do not guess a flag (e.g. "--dataset") -- launching
        # with no arguments is the only behavior we can state with
        # confidence. The staged workspace path is still logged and
        # returned so the user can point LichtFeld at it manually via its
        # own file picker; once the real CLI contract is known this can
        # launch fully wired.
        command: list[str] = []
        self.logger.info("LichtFeld launch command: %s %s", executable_path, command)

        try:
            started, pid = QProcess.startDetached(executable_path, command)
        except Exception as exc:  # never silently swallow
            self.logger.exception("Exception while launching LichtFeld: %s", exc)
            return LichtFeldLaunchResult(
                success=False, error=str(exc), staging=staging, executable_path=executable_path
            )

        self.logger.info("LichtFeld process start result: %s  PID: %s", started, pid)
        if not started:
            message = "LichtFeld process failed to start."
            self.logger.error(message)
            return LichtFeldLaunchResult(
                success=False, error=message, staging=staging, executable_path=executable_path
            )

        return LichtFeldLaunchResult(
            success=True, staging=staging, pid=pid, executable_path=executable_path, command=command
        )

    def prepare_scene(self, qc_result: QCResult) -> LichtFeldLaunchResult:
        """Validate + stage only -- does not launch LichtFeld. Used by
        the LichtFeld workspace's "Prepare Scene" action, which lets the
        user confirm the staged dataset looks right before opening the
        (interactive, GUI) LichtFeld application. Shares every check
        with ``send_to_lichtfeld`` via ``_validate_and_stage`` -- nothing
        is duplicated."""
        current = self._require_current()
        self.logger.info(
            "Prepare Scene requested. project_root=%s qc_state=%s registered=%s/%s",
            current.project_root, qc_result.state, qc_result.registered_images, qc_result.total_images,
        )
        return self._validate_and_stage(qc_result)

    def _validate_and_stage(self, qc_result: QCResult) -> LichtFeldLaunchResult:
        """Shared by ``send_to_lichtfeld`` and ``prepare_scene``: checks
        QC eligibility, the configured executable, and builds the
        temporary staging workspace. On success, ``executable_path`` and
        ``staging`` are populated and ``success`` is True (no launch has
        happened yet -- callers decide what to do next)."""
        current = self._require_current()

        if not qc_result.is_ready_for_lichtfeld:
            message = (
                f"Reconstruction QC state is {qc_result.state}, which is not eligible "
                f"for LichtFeld (requires READY or WARNING)."
            )
            self.logger.error(message)
            return LichtFeldLaunchResult(success=False, error=message)

        exe_ok, exe_path_or_message = self.validate_executable()
        self.logger.info("LichtFeld executable path: %s exists=%s", self.config.executable_path, exe_ok)
        if not exe_ok:
            self.logger.error(exe_path_or_message)
            return LichtFeldLaunchResult(success=False, error=exe_path_or_message)
        executable_path = exe_path_or_message

        image_source = self.image_source_path()
        sparse_model = self.sparse_model_path()
        self.logger.info("Image source path: %s", image_source)
        self.logger.info("Sparse model path: %s", sparse_model)

        try:
            staging = create_staging(image_source, sparse_model, current.data.name, current.data.version)
        except Exception as exc:  # never silently swallow
            self.logger.exception("Exception while creating LichtFeld staging: %s", exc)
            return LichtFeldLaunchResult(success=False, error=str(exc), executable_path=executable_path)

        self.logger.info("Temporary staging path: %s", staging.staging_root)
        self.logger.info("Image staging result: %s (%s)", staging.images_link.status, staging.images_link.message)
        self.logger.info("Sparse staging result: %s (%s)", staging.sparse_link.status, staging.sparse_link.message)
        self.logger.info(
            "Staged images accessible: %s  Staged sparse files present: %s",
            staging.images_accessible, staging.sparse_files_present,
        )

        if not staging.ok:
            self.logger.error("LichtFeld staging failed: %s", staging.error)
            return LichtFeldLaunchResult(
                success=False, error=staging.error, staging=staging, executable_path=executable_path
            )

        return LichtFeldLaunchResult(success=True, staging=staging, executable_path=executable_path)
