"""Application and per-project logging setup.

Two kinds of logs exist:

* The **application log**, which lives in the user config directory and
  captures everything from process start (before any project is open).
* **Per-project logs** (``application.log``, ``colmap.log``,
  ``lichtfeld.log``, ``render.log``), which live under
  ``<projectRoot>/logs`` once a project is loaded.

The GUI Logs page tails these files; nothing here talks to Qt directly so
it can be unit tested and reused by any future headless/CLI mode.
"""

from __future__ import annotations

import logging
from pathlib import Path

APP_LOGGER_NAME = "local3dgsstudio"

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_app_logger() -> logging.Logger:
    """Return the singleton application logger (console handler only)."""
    logger = logging.getLogger(APP_LOGGER_NAME)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
        logger.addHandler(console)
    return logger


def attach_file_handler(logger: logging.Logger, log_file: Path) -> logging.Handler:
    """Attach (and return) a file handler writing to ``log_file``.

    Safe to call multiple times with different files (e.g. once per opened
    project) -- each call adds a new handler; callers that want to replace
    a previous project's handler should remove it first via
    ``logger.removeHandler``.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    logger.addHandler(handler)
    return handler


def get_named_logger(name: str, log_file: Path | None = None) -> logging.Logger:
    """Return a child logger (e.g. 'colmap', 'lichtfeld') with its own file."""
    logger = logging.getLogger(f"{APP_LOGGER_NAME}.{name}")
    logger.setLevel(logging.DEBUG)
    if log_file is not None:
        attach_file_handler(logger, log_file)
    return logger
