"""Non-blocking external process execution, built on QProcess.

Not exercised by any COLMAP/LichtFeld workflow yet (that's phase04/05) --
included now because the GUI (Logs page) and Settings ("test detected
path") benefit from a single, well-behaved process runner from day one.

Every process run emits its command line, stdout, stderr, and exit status
through Qt signals, satisfying "show command before execution" and "never
hide errors".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal


@dataclass
class ProcessResult:
    command: str
    exit_code: int
    exit_status: str  # "NormalExit" | "CrashExit"
    stdout: str
    stderr: str


class ManagedProcess(QObject):
    """Wraps a single QProcess run with live output streaming.

    Usage::

        proc = ManagedProcess()
        proc.output_line.connect(on_output_line)
        proc.finished_result.connect(on_finished)
        proc.start("colmap.bat", ["feature_extractor", ...], cwd=project_dir)
    """

    started_with_command = Signal(str)
    output_line = Signal(str)
    error_line = Signal(str)
    finished_result = Signal(object)  # ProcessResult

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._stdout_buffer: list[str] = []
        self._stderr_buffer: list[str] = []
        self._command_display = ""

    def start(self, executable: str, arguments: list[str], cwd: Path | None = None) -> None:
        self._stdout_buffer.clear()
        self._stderr_buffer.clear()
        self._command_display = " ".join([executable, *arguments])
        if cwd is not None:
            self._process.setWorkingDirectory(str(cwd))
        self.started_with_command.emit(self._command_display)
        self._process.start(executable, arguments)

    def cancel(self) -> None:
        """Ask the process to terminate gracefully."""
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.terminate()

    def kill(self) -> None:
        """Force-kill the process immediately."""
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    def is_running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def _on_stdout(self) -> None:
        text = bytes(self._process.readAllStandardOutput()).decode(errors="replace")
        for line in text.splitlines():
            self._stdout_buffer.append(line)
            self.output_line.emit(line)

    def _on_stderr(self) -> None:
        text = bytes(self._process.readAllStandardError()).decode(errors="replace")
        for line in text.splitlines():
            self._stderr_buffer.append(line)
            self.error_line.emit(line)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        status_name = "NormalExit" if exit_status == QProcess.ExitStatus.NormalExit else "CrashExit"
        result = ProcessResult(
            command=self._command_display,
            exit_code=exit_code,
            exit_status=status_name,
            stdout="\n".join(self._stdout_buffer),
            stderr="\n".join(self._stderr_buffer),
        )
        self.finished_result.emit(result)
