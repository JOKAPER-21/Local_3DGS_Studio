"""Reusable pipeline-step status row: Database / Features / Matching /
Mapper / Analysis, each colored by status (per the specification's
``pipelineUi.visualStatus`` values: Not Started, Running, Completed,
Failed)."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

STATUS_NOT_STARTED = "Not Started"
STATUS_RUNNING = "Running"
STATUS_COMPLETED = "Completed"
STATUS_FAILED = "Failed"

_STATUS_OBJECT_NAMES = {
    STATUS_NOT_STARTED: "statusMuted",
    STATUS_RUNNING: "statusWarning",
    STATUS_COMPLETED: "statusOk",
    STATUS_FAILED: "statusError",
}

STEP_NAMES = ["Database", "Features", "Matching", "Mapper", "Analysis"]


class ColmapPipelineWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._value_labels: dict[str, QLabel] = {}

        for name in STEP_NAMES:
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            title = QLabel(name)
            title.setObjectName("sectionLabel")
            value = QLabel(STATUS_NOT_STARTED)
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            layout.addWidget(card)
            self._value_labels[name] = value

        self.set_all(STATUS_NOT_STARTED)

    def set_status(self, step: str, status: str) -> None:
        label = self._value_labels[step]
        label.setText(status)
        label.setObjectName(_STATUS_OBJECT_NAMES.get(status, "statusMuted"))
        label.style().unpolish(label)
        label.style().polish(label)

    def set_all(self, status: str) -> None:
        for step in STEP_NAMES:
            self.set_status(step, status)

    def apply_reconstruction_state(self, state) -> None:
        """Reflect a ``ReconstructionState`` (file/flag-derived truth) in
        the status row. Does not distinguish "never run" from "in
        progress" -- callers set ``Running``/``Failed`` themselves while a
        step is actually executing."""
        self.set_status("Database", STATUS_COMPLETED if state.database_created else STATUS_NOT_STARTED)
        self.set_status("Features", STATUS_COMPLETED if state.features_extracted else STATUS_NOT_STARTED)
        self.set_status("Matching", STATUS_COMPLETED if state.features_matched else STATUS_NOT_STARTED)
        self.set_status("Mapper", STATUS_COMPLETED if state.mapper_completed else STATUS_NOT_STARTED)
        self.set_status("Analysis", STATUS_COMPLETED if state.analysis_completed else STATUS_NOT_STARTED)
