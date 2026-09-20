"""``ReconstructionState``: what stage a project's COLMAP reconstruction
has actually reached.

Per the specification, state must be derived from real evidence -- actual
files on disk plus a completed process's persisted result -- never merely
because a process was *started*. Feature extraction and matching don't
produce a distinct output file of their own (they mutate ``database.db``
in place), so those two stages are corroborated by the ``completed`` flag
that ``COLMAPManager`` only sets after a zero exit code, combined with
``database.db`` actually existing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STATE_NOT_STARTED = "NOT_STARTED"
STATE_DATABASE_CREATED = "DATABASE_CREATED"
STATE_FEATURES_EXTRACTED = "FEATURES_EXTRACTED"
STATE_FEATURES_MATCHED = "FEATURES_MATCHED"
STATE_SPARSE_RECONSTRUCTION_CREATED = "SPARSE_RECONSTRUCTION_CREATED"
STATE_ANALYZED = "ANALYZED"
STATE_READY = "READY"

REQUIRED_SPARSE_FILES = ("cameras.bin", "images.bin", "points3D.bin")


@dataclass
class ReconstructionState:
    database_created: bool = False
    features_extracted: bool = False
    features_matched: bool = False
    mapper_completed: bool = False
    analysis_completed: bool = False
    state: str = STATE_NOT_STARTED


def sparse_model_files_exist(sparse_model_path: Path) -> bool:
    return all((sparse_model_path / name).exists() for name in REQUIRED_SPARSE_FILES)


def derive_reconstruction_state(
    database_path: Path, sparse_model_path: Path, colmap_info: dict
) -> ReconstructionState:
    """Compute the current stage from disk evidence and previously
    persisted (process-verified) completion flags."""
    database_created = database_path.exists() and database_path.stat().st_size > 0

    feature_extraction = colmap_info.get("featureExtraction", {}) or {}
    feature_matching = colmap_info.get("featureMatching", {}) or {}
    analysis = colmap_info.get("analysis", {}) or {}

    features_extracted = database_created and bool(feature_extraction.get("completed"))
    features_matched = features_extracted and bool(feature_matching.get("completed"))
    mapper_completed = sparse_model_files_exist(sparse_model_path)
    analysis_completed = mapper_completed and bool(analysis.get("completed"))

    if analysis_completed:
        total = analysis.get("totalImages", 0)
        registered = analysis.get("registeredImages", 0)
        state = STATE_READY if total > 0 and registered == total else STATE_ANALYZED
    elif mapper_completed:
        state = STATE_SPARSE_RECONSTRUCTION_CREATED
    elif features_matched:
        state = STATE_FEATURES_MATCHED
    elif features_extracted:
        state = STATE_FEATURES_EXTRACTED
    elif database_created:
        state = STATE_DATABASE_CREATED
    else:
        state = STATE_NOT_STARTED

    return ReconstructionState(
        database_created=database_created,
        features_extracted=features_extracted,
        features_matched=features_matched,
        mapper_completed=mapper_completed,
        analysis_completed=analysis_completed,
        state=state,
    )
