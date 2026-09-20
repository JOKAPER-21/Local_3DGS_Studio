"""Launches a ``ColmapCommand`` (built by ``COLMAPManager``) through the
existing ``ManagedProcess`` (QProcess) wrapper from Phase 01.

Deliberately thin: all command construction lives in
``colmap_manager.py``, and all non-blocking execution machinery already
lives in ``process_manager.ManagedProcess``. This module's only job is
to connect the two without creating a second process-execution system.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.core.colmap_manager import ColmapCommand
from src.core.process_manager import ManagedProcess


def start_colmap_command(
    process: ManagedProcess, command: ColmapCommand, cwd: Optional[Path] = None
) -> None:
    """Start ``command`` on an already-constructed ``ManagedProcess``.

    The caller owns ``process`` (connects its signals, decides its
    parent) -- this just starts it with the right executable/arguments
    for the given COLMAP command, cd'd into ``cwd`` if given (typically
    the project root, so relative log paths behave predictably)."""
    process.start(command.executable, command.process_arguments, cwd=cwd)
