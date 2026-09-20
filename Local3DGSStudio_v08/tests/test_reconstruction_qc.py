"""Tests for ``ReconstructionQC``: file-evidence validation, metric
collection, camera model/distortion detection, and state evaluation --
built entirely on real files on disk (via a temp project) plus a fake
COLMAP CLI-free ``project.json`` state, never a live COLMAP process.
"""

from __future__ import annotations

import struct
from pathlib import Path

from src.core.config_manager import ConfigManager
from src.core.project_manager import ProjectManager
from src.core.reconstruction_qc import (
    QC_STATE_FAILED,
    QC_STATE_NOT_READY,
    QC_STATE_READY,
    QC_STATE_WARNING,
    ReconstructionQC,
)

_BASELINE_ANALYSIS = {
    "completed": True,
    "cameras": 1,
    "images": 293,
    "totalImages": 293,
    "registeredImages": 293,
    "points": 139741,
    "observations": 1731278,
    "meanTrackLength": 12.389191,
    "meanObservationsPerImage": 5908.798635,
    "meanReprojectionError": 0.937114,
}


def _write_cameras_bin(path: Path, cameras: list[tuple[int, int, int, int, list[float]]]) -> None:
    with open(path, "wb") as handle:
        handle.write(struct.pack("<Q", len(cameras)))
        for camera_id, model_id, width, height, params in cameras:
            handle.write(struct.pack("<iiQQ", camera_id, model_id, width, height))
            for value in params:
                handle.write(struct.pack("<d", value))


def _new_project(tmp_path: Path):
    config = ConfigManager(tmp_path / "appConfig")
    manager = ProjectManager(config)
    opened = manager.create_project(str(tmp_path / "projects"), "gsOfficeBuildingPillar", "v01")
    return manager, opened


def _set_up_reconstruction(
    opened,
    *,
    analysis: dict | None = None,
    camera_model_id: int = 2,  # SIMPLE_RADIAL
    database_bytes: bytes = b"sqlite-fake-bytes",
    write_sparse_files: bool = True,
) -> None:
    """Populate a project's colmap/v01 folder with real files so QC reads
    real disk evidence, exactly as Phase 04 would leave it after a
    successful pipeline run. COLMAP reads rawData/images/vNN directly --
    there is no colmap/vNN/images junction to create."""
    resolver = opened.resolver
    colmap_dir = resolver.colmap
    colmap_dir.mkdir(parents=True, exist_ok=True)

    if database_bytes is not None:
        (colmap_dir / "database.db").write_bytes(database_bytes)

    sparse_model = colmap_dir / "sparse" / "0"
    if write_sparse_files:
        sparse_model.mkdir(parents=True, exist_ok=True)
        (sparse_model / "images.bin").write_bytes(b"fake-images-bin")
        (sparse_model / "points3D.bin").write_bytes(b"fake-points3d-bin")
        _write_cameras_bin(
            sparse_model / "cameras.bin",
            [(1, camera_model_id, 1920, 1080, [1400.0, 960.0, 540.0, -0.05][: {0: 3, 1: 4, 2: 4}.get(camera_model_id, 4)])],
        )

    if analysis is not None:
        opened.data.colmap_info["analysis"] = analysis
        opened.data.colmap_info["featureExtraction"] = {"completed": True}
        opened.data.colmap_info["featureMatching"] = {"completed": True}


def _write_fake_source_images(opened, count: int = 3) -> None:
    """Populate the authoritative rawData/images/vNN directory with a
    few placeholder files -- QC's image_source_valid check requires the
    directory to exist AND be non-empty."""
    images_dir = opened.resolver.images
    images_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (images_dir / f"img_{i:04d}.jpg").write_bytes(b"fake jpg bytes")


# ---------------------------------------------------------------------------
# Happy path / reference baseline
# ---------------------------------------------------------------------------


def test_qc_293_registered_images(tmp_path):
    manager, opened = _new_project(tmp_path)
    resolver = opened.resolver
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS))

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.total_images == 293
    assert result.registered_images == 293
    assert result.registration_percentage == 100.0
    assert result.points == 139741
    assert result.observations == 1731278
    assert round(result.mean_track_length, 3) == 12.389
    assert round(result.mean_reprojection_error_px, 3) == 0.937
    assert result.camera_models == ["SIMPLE_RADIAL"]
    assert result.distorted_camera_models == ["SIMPLE_RADIAL"]
    assert result.state == QC_STATE_READY  # distortion is a warning-free READY per spec... see below


def test_qc_ready_state_reference_dataset(tmp_path):
    """Distortion alone must not push a fully-registered, low-error
    reconstruction out of READY -- it's reported, not penalized."""
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS))

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_READY
    assert result.errors == []
    assert any("Distorted camera model" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Partial registration -> WARNING
# ---------------------------------------------------------------------------


def test_qc_partial_registration(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    analysis = dict(_BASELINE_ANALYSIS)
    analysis["registeredImages"] = 146
    _set_up_reconstruction(opened, analysis=analysis, camera_model_id=1)  # PINHOLE, no distortion

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_WARNING
    assert result.registered_images == 146
    assert round(result.registration_percentage, 2) == 49.83
    assert any("146 of 293" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Missing evidence -> FAILED
# ---------------------------------------------------------------------------


def test_qc_zero_registered_images(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    analysis = dict(_BASELINE_ANALYSIS)
    analysis["registeredImages"] = 0
    _set_up_reconstruction(opened, analysis=analysis)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_FAILED
    assert any("No images were registered" in e for e in result.errors)


def test_qc_missing_database(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS), database_bytes=None)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_FAILED
    assert result.database_valid is False
    assert any("database" in e.lower() for e in result.errors)


def test_qc_empty_database(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS), database_bytes=b"")
    # write_bytes(b"") still creates the file but with size 0.

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.database_valid is False
    assert result.state == QC_STATE_FAILED


def test_qc_missing_sparse_model(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(
        opened, analysis=dict(_BASELINE_ANALYSIS), write_sparse_files=False
    )

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.required_files_present is False
    assert result.state == QC_STATE_FAILED


def test_qc_missing_cameras_bin(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS))
    (opened.resolver.colmap / "sparse" / "0" / "cameras.bin").unlink()

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.required_files_present is False
    assert result.state == QC_STATE_FAILED


def test_qc_missing_images_bin(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS))
    (opened.resolver.colmap / "sparse" / "0" / "images.bin").unlink()

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.required_files_present is False
    assert result.state == QC_STATE_FAILED


def test_qc_missing_points3d_bin(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS))
    (opened.resolver.colmap / "sparse" / "0" / "points3D.bin").unlink()

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.required_files_present is False
    assert result.state == QC_STATE_FAILED


def test_qc_zero_points(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    analysis = dict(_BASELINE_ANALYSIS)
    analysis["points"] = 0
    _set_up_reconstruction(opened, analysis=analysis)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_FAILED
    assert any("zero points" in e.lower() for e in result.errors)


def test_qc_missing_image_source(tmp_path):
    """COLMAP reads rawData/images/vNN directly -- if that directory is
    missing or empty, QC must fail rather than silently accepting a
    reconstruction whose actual input images can no longer be found."""
    manager, opened = _new_project(tmp_path)
    # Deliberately do NOT call _write_fake_source_images: the directory
    # either doesn't exist yet or is empty.
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS))

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.image_source_valid is False
    assert result.state == QC_STATE_FAILED


# ---------------------------------------------------------------------------
# Quality warnings (never hard failures)
# ---------------------------------------------------------------------------


def test_qc_high_reprojection_error(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    analysis = dict(_BASELINE_ANALYSIS)
    analysis["meanReprojectionError"] = 2.5
    _set_up_reconstruction(opened, analysis=analysis, camera_model_id=1)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_WARNING
    assert any("reprojection error is high" in w.lower() for w in result.warnings)


def test_qc_low_track_length(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    analysis = dict(_BASELINE_ANALYSIS)
    analysis["meanTrackLength"] = 1.5
    _set_up_reconstruction(opened, analysis=analysis, camera_model_id=1)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_WARNING
    assert any("track length is short" in w.lower() for w in result.warnings)


def test_qc_camera_distortion_detection(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS), camera_model_id=2)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.camera_models == ["SIMPLE_RADIAL"]
    assert result.distorted_camera_models == ["SIMPLE_RADIAL"]
    # Distortion is informational: it must not turn an otherwise-healthy
    # fully-registered reconstruction into anything worse than WARNING.
    assert result.state in (QC_STATE_READY, QC_STATE_WARNING)
    assert result.errors == []


def test_qc_no_distortion_for_pinhole(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS), camera_model_id=1)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.distorted_camera_models == []
    assert result.state == QC_STATE_READY


# ---------------------------------------------------------------------------
# NOT_READY: nothing attempted yet
# ---------------------------------------------------------------------------


def test_qc_not_ready_state(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    # No database, no sparse reconstruction -- nothing has been run yet.

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_NOT_READY
    assert result.errors == []
    assert result.warnings == []


# ---------------------------------------------------------------------------
# Missing metrics are never silently treated as zero
# ---------------------------------------------------------------------------


def test_qc_missing_metric_not_treated_as_zero(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    analysis = dict(_BASELINE_ANALYSIS)
    del analysis["meanReprojectionError"]
    _set_up_reconstruction(opened, analysis=analysis, camera_model_id=1)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.mean_reprojection_error_px is None
    assert any("reprojection error is not available" in w.lower() for w in result.warnings)
    # An unavailable (not zero) metric is a warning, never silently
    # ignored or coerced into "0.0px, which would look great".
    assert result.state == QC_STATE_WARNING


def test_qc_no_analysis_yet_but_sparse_files_exist(tmp_path):
    """Sparse files present (e.g. mapper ran) but model_analyzer never
    completed -- metrics must come back empty, and QC must not fabricate
    'No images were registered.' from that absence. Files look valid, so
    this is a WARNING (metrics unavailable), never a FAILED verdict --
    that message is reserved for an explicitly parsed zero."""
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=None)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.total_images == 0
    assert result.registered_images == 0
    assert result.metrics_parsed is False
    assert result.state == QC_STATE_WARNING
    assert not any("No images were registered" in e for e in result.errors)
    assert any("metrics are not available" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# ProjectPathResolver usage / project.json persistence
# ---------------------------------------------------------------------------


def test_qc_uses_project_resolver_paths(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS))

    qc = ReconstructionQC(manager)

    assert qc.colmap_manager.database_path() == opened.resolver.colmap / "database.db"
    assert qc.colmap_manager.sparse_model_path() == opened.resolver.colmap / "sparse" / "0"
    assert qc.colmap_manager.active_image_source_path() == opened.resolver.images


def test_qc_project_json_update(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_BASELINE_ANALYSIS))

    qc = ReconstructionQC(manager)
    result = qc.run()

    # Re-read project.json from disk to confirm it was actually persisted
    # (not just held in memory), and that existing sections survive.
    from src.core.project_json import read_project_json

    reloaded = read_project_json(opened.project_root)
    assert reloaded.reconstruction_qc_info["state"] == QC_STATE_READY
    assert reloaded.reconstruction_qc_info["registeredImages"] == 293
    assert reloaded.reconstruction_qc_info["points"] == 139741
    # Phase 04's colmap section must still be present, untouched.
    assert reloaded.colmap_info["analysis"]["completed"] is True
    assert reloaded.name == "gsOfficeBuildingPillar"


def test_qc_state_transitions(tmp_path):
    """One project, walked through NOT_READY -> FAILED -> WARNING ->
    READY as evidence is incrementally added -- confirms QC always
    re-evaluates from current disk/metric state rather than caching."""
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    qc = ReconstructionQC(manager)

    assert qc.run().state == QC_STATE_NOT_READY

    analysis = dict(_BASELINE_ANALYSIS)
    analysis["registeredImages"] = 0
    _set_up_reconstruction(opened, analysis=analysis, camera_model_id=1)
    assert qc.run().state == QC_STATE_FAILED

    analysis["registeredImages"] = 146
    opened.data.colmap_info["analysis"] = analysis
    assert qc.run().state == QC_STATE_WARNING

    analysis["registeredImages"] = 293
    opened.data.colmap_info["analysis"] = analysis
    assert qc.run().state == QC_STATE_READY


# ---------------------------------------------------------------------------
# Regression coverage for the "missing metric treated as zero" bug
# ---------------------------------------------------------------------------


_UPDATED_REFERENCE_ANALYSIS = {
    "completed": True,
    "cameras": 293,
    "rigs": 293,
    "frames": 293,
    "registeredFrames": 293,
    "images": 293,
    "totalImages": 293,
    "registeredImages": 293,
    "points": 140050,
    "observations": 1733420,
    "meanTrackLength": 12.377151,
    "meanObservationsPerImage": 5916.109215,
    "meanReprojectionError": 0.940535,
}


def test_explicit_zero_registration_is_failed(tmp_path):
    """An *explicitly parsed* zero is still a genuine failure -- the fix
    for the missing-metric bug must not accidentally soften this case."""
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    analysis = dict(_UPDATED_REFERENCE_ANALYSIS)
    analysis["registeredImages"] = 0
    _set_up_reconstruction(opened, analysis=analysis, camera_model_id=1)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.metrics_parsed is True
    assert result.state == QC_STATE_FAILED
    assert any("No images were registered." in e for e in result.errors)


def test_missing_metrics_are_not_zero(tmp_path):
    """Analysis marked completed but with no usable metrics (parser
    failure) must never produce 'No images were registered.' -- that
    phrasing is reserved for an explicit zero (see test above)."""
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis={"completed": True})

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.metrics_parsed is False
    assert result.state == QC_STATE_WARNING
    assert not any("No images were registered" in e for e in result.errors)


def test_simple_radial_does_not_fail_reconstruction(tmp_path):
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_UPDATED_REFERENCE_ANALYSIS), camera_model_id=2)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.camera_models == ["SIMPLE_RADIAL"]
    assert result.state == QC_STATE_READY
    assert result.errors == []


def test_current_project_reference_metrics(tmp_path):
    """The exact dataset from the bug report: 293/293 registered,
    140,050 points, 1,733,420 observations, mean track length
    12.377151, mean reprojection error 0.940535px, SIMPLE_RADIAL. Must
    resolve to READY, not FAILED."""
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_UPDATED_REFERENCE_ANALYSIS), camera_model_id=2)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_READY
    assert result.registered_images == 293
    assert result.total_images == 293
    assert result.registration_percentage == 100.0
    assert result.points == 140050
    assert result.observations == 1733420
    assert result.mean_track_length == 12.377151
    assert result.mean_observations_per_image == 5916.109215
    assert result.mean_reprojection_error_px == 0.940535
    assert result.camera_models == ["SIMPLE_RADIAL"]
    assert result.distorted_camera_models == ["SIMPLE_RADIAL"]
    assert any("Distorted camera model" in w for w in result.warnings)
    assert not any("No images were registered" in e for e in result.errors)


def test_qc_ready_when_293_of_293_registered(tmp_path):
    """Exact-named regression test requested for this bug fix: once
    metrics are actually parsed (the output-capture fix), 293/293 must
    resolve to READY, not WARNING or FAILED."""
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    _set_up_reconstruction(opened, analysis=dict(_UPDATED_REFERENCE_ANALYSIS), camera_model_id=2)

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_READY
    assert result.registered_images == 293
    assert result.total_images == 293
    assert result.registration_percentage == 100.0


# ---------------------------------------------------------------------------
# The user's specific "367/367, SIMPLE_RADIAL, reprojection 1.117px" report
# ---------------------------------------------------------------------------


def test_qc_367_of_367_simple_radial_high_reprojection_is_warning_not_because_of_distortion(tmp_path):
    """Reproduces the exact numbers from the bug report. The reconstruction
    IS correctly WARNING (not a bug) -- but the cause must be the 1.117px
    mean reprojection error exceeding the 1.0px normal-reference threshold,
    never the SIMPLE_RADIAL camera model itself. If SIMPLE_RADIAL alone
    were causing WARNING, that would be the real bug; it is not."""
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    analysis = {
        "completed": True,
        "totalImages": 367,
        "registeredImages": 367,
        "points": 174276,
        "observations": 1237244,
        "meanTrackLength": 7.099337,
        "meanObservationsPerImage": 3371.237057,
        "meanReprojectionError": 1.116929,
    }
    _set_up_reconstruction(opened, analysis=analysis, camera_model_id=2)  # SIMPLE_RADIAL

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_WARNING
    assert result.registration_percentage == 100.0
    # The distortion note is present (informational)...
    assert any("Distorted camera model" in w for w in result.warnings)
    # ...but the thing that actually set WARNING is the reprojection error.
    assert any("reprojection error" in w.lower() for w in result.warnings)
    assert result.is_ready_for_lichtfeld  # WARNING still allows Send to LichtFeld


def test_qc_367_of_367_simple_radial_low_reprojection_is_ready(tmp_path):
    """Same dataset, but with reprojection error at/under the 1.0px
    threshold -- confirms SIMPLE_RADIAL truly never blocks READY on its
    own, once the only other quality signal is out of the way."""
    manager, opened = _new_project(tmp_path)
    _write_fake_source_images(opened)
    analysis = {
        "completed": True,
        "totalImages": 367,
        "registeredImages": 367,
        "points": 174276,
        "observations": 1237244,
        "meanTrackLength": 7.099337,
        "meanObservationsPerImage": 3371.237057,
        "meanReprojectionError": 0.937114,
    }
    _set_up_reconstruction(opened, analysis=analysis, camera_model_id=2)  # SIMPLE_RADIAL

    qc = ReconstructionQC(manager)
    result = qc.run()

    assert result.state == QC_STATE_READY
    assert result.camera_models == ["SIMPLE_RADIAL"]
    assert any("Distorted camera model" in w for w in result.warnings)
