"""Tests for ``ManagedProcess``, focused on the output-capture bug found
while debugging Reconstruction QC: a short-lived process (like COLMAP's
``model_analyzer``, which prints its whole summary and exits almost
immediately) can have its final chunk of output dropped if ``finished``
fires without an accompanying final ``readyRead*`` signal for that last
chunk -- a documented QProcess race. These tests run real subprocesses
(not mocks) that print output and exit immediately, repeatedly, to catch
that race rather than assume it away.
"""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from src.core.process_manager import ManagedProcess, ProcessResult


@pytest.fixture(scope="module")
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


def _run_and_capture(qt_app, executable: str, arguments: list[str], timeout_ms: int = 5000) -> ProcessResult:
    proc = ManagedProcess()
    loop = QEventLoop()
    captured: dict[str, ProcessResult] = {}

    def on_finished(result: ProcessResult) -> None:
        captured["result"] = result
        loop.quit()

    proc.finished_result.connect(on_finished)
    proc.start(executable, arguments)

    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)
    timeout_timer.timeout.connect(loop.quit)
    timeout_timer.start(timeout_ms)
    loop.exec()

    if "result" not in captured:
        pytest.fail("Process did not finish within the timeout.")
    return captured["result"]


def test_captures_stdout_written_immediately_before_exit(qt_app):
    """A process that prints to stdout and exits with (essentially) no
    delay must still have every line captured -- this is exactly the
    shape of COLMAP's model_analyzer output."""
    script = (
        "import sys; "
        "print('Registered images: 293'); "
        "print('Points: 140050'); "
        "sys.stdout.flush()"
    )
    result = _run_and_capture(qt_app, sys.executable, ["-c", script])

    assert result.exit_code == 0
    assert "Registered images: 293" in result.stdout
    assert "Points: 140050" in result.stdout


def test_captures_stderr_written_immediately_before_exit(qt_app):
    """Same race, but on the stderr channel -- glog-based tools (which
    is what COLMAP uses) commonly log INFO-level output to stderr."""
    script = (
        "import sys; "
        "print('Registered images: 293', file=sys.stderr); "
        "print('Mean reprojection error: 0.940535px', file=sys.stderr); "
        "sys.stderr.flush()"
    )
    result = _run_and_capture(qt_app, sys.executable, ["-c", script])

    assert result.exit_code == 0
    assert "Registered images: 293" in result.stderr
    assert "Mean reprojection error: 0.940535px" in result.stderr


def test_captures_trailing_output_across_many_quick_runs(qt_app):
    """Run the fire-and-immediately-exit case many times in a row: the
    race, if present, doesn't reproduce on every single run, so a
    regression test needs enough repetitions to be a meaningful guard
    rather than assert on one lucky pass."""
    script = "print('Registered images: 293')"
    for _ in range(25):
        result = _run_and_capture(qt_app, sys.executable, ["-c", script])
        assert "Registered images: 293" in result.stdout


def test_captures_output_on_both_channels_simultaneously(qt_app):
    """A process that writes to both stdout and stderr right before
    exiting must have both channels fully captured -- this is why
    colmap_panel.py concatenates result.stdout + result.stderr before
    handing text to the parser, regardless of which channel COLMAP
    actually used for a given build."""
    script = (
        "import sys; "
        "print('Images: 293'); "
        "print('Registered images: 293', file=sys.stderr); "
        "sys.stdout.flush(); sys.stderr.flush()"
    )
    result = _run_and_capture(qt_app, sys.executable, ["-c", script])

    assert "Images: 293" in result.stdout
    assert "Registered images: 293" in result.stderr
