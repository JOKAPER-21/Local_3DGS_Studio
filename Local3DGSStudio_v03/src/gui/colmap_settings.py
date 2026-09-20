"""Small form for the per-run COLMAP settings: GPU toggles, CPU thread
count, and matcher choice. Phase 04 defaults to CPU-only, matching the
configuration already proven to work on the reference machine."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QSpinBox, QWidget

from src.core.colmap_config import COLMAPConfig


class ColmapSettingsWidget(QWidget):
    def __init__(self, config: COLMAPConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.fe_gpu_checkbox = QCheckBox("Use GPU for Feature Extraction")
        self.fe_gpu_checkbox.setChecked(config.feature_extraction_use_gpu)
        layout.addRow(self.fe_gpu_checkbox)

        self.threads_spin = QSpinBox()
        self.threads_spin.setMinimum(1)
        self.threads_spin.setMaximum(64)
        self.threads_spin.setValue(config.feature_extraction_threads)
        layout.addRow("CPU Threads", self.threads_spin)

        self.matcher_combo = QComboBox()
        self.matcher_combo.addItems(["Exhaustive"])
        layout.addRow("Matcher", self.matcher_combo)

        self.fm_gpu_checkbox = QCheckBox("Use GPU for Feature Matching")
        self.fm_gpu_checkbox.setChecked(config.feature_matching_use_gpu)
        layout.addRow(self.fm_gpu_checkbox)

    def apply_to_config(self, config: COLMAPConfig) -> COLMAPConfig:
        """Return a copy of ``config`` with the executable path preserved
        and every other field taken from the current form state."""
        return COLMAPConfig(
            executable_path=config.executable_path,
            feature_extraction_use_gpu=self.fe_gpu_checkbox.isChecked(),
            feature_extraction_threads=self.threads_spin.value(),
            feature_matching_use_gpu=self.fm_gpu_checkbox.isChecked(),
            matcher_type="exhaustive",
        )
