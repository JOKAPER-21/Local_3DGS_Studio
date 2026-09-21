"""``COLMAPConfig``: the run-time settings for one COLMAP pipeline
execution (GPU toggles, thread count, matcher choice).

This is intentionally separate from the *detected* executable path
(handled by ``software_detector`` / ``ConfigManager``) -- it only carries
the knobs a user might change per run, with the CPU-only defaults proven
to work on the reference machine.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class COLMAPConfig:
    executable_path: str = ""

    # Phase 04 default: CPU-only. Proven to work; GPU is opt-in later.
    feature_extraction_use_gpu: bool = False
    feature_extraction_threads: int = 4

    feature_matching_use_gpu: bool = False
    matcher_type: str = "exhaustive"  # only 'exhaustive' is implemented in phase 04

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_project_colmap_info(
        cls, colmap_info: dict, executable_path: str = ""
    ) -> "COLMAPConfig":
        """Rebuild the last-used settings from project.json's ``colmap``
        section, so reopening a project restores what was actually run."""
        feature_extraction = colmap_info.get("featureExtraction", {}) or {}
        feature_matching = colmap_info.get("featureMatching", {}) or {}
        return cls(
            executable_path=executable_path,
            feature_extraction_use_gpu=bool(feature_extraction.get("useGPU", False)),
            feature_extraction_threads=int(feature_extraction.get("numThreads", 4) or 4),
            feature_matching_use_gpu=bool(feature_matching.get("useGPU", False)),
            matcher_type=feature_matching.get("method", "exhaustive") or "exhaustive",
        )
