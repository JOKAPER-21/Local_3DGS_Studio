import struct

import pytest

from src.utils.colmap_parser import (
    CameraModelInfo,
    ColmapParseError,
    calculate_registration_percentage,
    parse_cameras_bin,
    parse_model_analyzer_output,
    parse_version_output,
)

_VERSION_OUTPUT = "COLMAP 4.2.0 (Commit be5e291 on 2026-08-31 with CUDA)"

_MODEL_ANALYZER_OUTPUT = """
Cameras: 1
Images: 293
Registered images: 293
Points: 139741
Observations: 1731278
Mean track length: 12.389191
Mean observations per image: 5908.798635
Mean reprojection error: 0.937114px
"""


def test_parse_version_output_extracts_version_and_cuda():
    parsed = parse_version_output(_VERSION_OUTPUT)
    assert parsed["version"] == "4.2.0"
    assert parsed["cuda_build"] is True


def test_parse_version_output_without_cuda():
    parsed = parse_version_output("COLMAP 4.2.0 (Commit be5e291 on 2026-08-31)")
    assert parsed["version"] == "4.2.0"
    assert parsed["cuda_build"] is False


def test_parse_version_output_no_match():
    parsed = parse_version_output("garbage output, not colmap at all")
    assert parsed["version"] == ""
    assert parsed["cuda_build"] is False


def test_parse_model_analyzer_output_matches_known_baseline():
    metrics = parse_model_analyzer_output(_MODEL_ANALYZER_OUTPUT)
    assert metrics["registeredImages"] == 293
    assert metrics["totalImages"] == 293
    assert metrics["points"] == 139741
    assert metrics["observations"] == 1731278
    assert metrics["meanTrackLength"] == 12.389191
    assert metrics["meanReprojectionError"] == 0.937114


def test_parse_model_analyzer_output_missing_lines_are_absent():
    metrics = parse_model_analyzer_output("Cameras: 1\nImages: 10\n")
    assert "registeredImages" not in metrics
    assert metrics["totalImages"] == 10


def test_model_analyzer_parses_all_metrics_with_glog_prefixes():
    """Real COLMAP (glog) output prefixes every line with a timestamp,
    thread id, and source location, e.g.
    'I0917 12:00:00.123456 12345 model_analyzer.cc:73] '. A regex
    anchored to the start of the line never matches this -- this is the
    exact bug that caused Reconstruction QC to see an empty metrics dict
    and report 'No images were registered.' for a healthy 293/293
    reconstruction."""
    text = "\n".join(
        f"I0917 12:00:00.123456 12345 model_analyzer.cc:{70 + i}] {line}"
        for i, line in enumerate([
            "Rigs: 293",
            "Cameras: 293",
            "Frames: 293",
            "Registered frames: 293",
            "Images: 293",
            "Registered images: 293",
            "Points: 140050",
            "Observations: 1733420",
            "Mean track length: 12.377151",
            "Mean observations per image: 5916.109215",
            "Mean reprojection error: 0.940535px",
        ])
    )

    metrics = parse_model_analyzer_output(text)

    assert metrics["rigs"] == 293
    assert metrics["cameras"] == 293
    assert metrics["frames"] == 293
    assert metrics["registeredFrames"] == 293
    assert metrics["images"] == 293
    assert metrics["totalImages"] == 293
    assert metrics["registeredImages"] == 293
    assert metrics["points"] == 140050
    assert metrics["observations"] == 1733420
    assert metrics["meanTrackLength"] == 12.377151
    assert metrics["meanObservationsPerImage"] == 5916.109215
    assert metrics["meanReprojectionError"] == 0.940535


def test_model_analyzer_parses_all_metrics_without_prefixes():
    """The same metrics, in the plain (no-glog-prefix) form used by
    other fixtures in this file -- both forms must parse identically."""
    text = (
        "Rigs: 293\nCameras: 293\nFrames: 293\nRegistered frames: 293\n"
        "Images: 293\nRegistered images: 293\nPoints: 140050\n"
        "Observations: 1733420\nMean track length: 12.377151\n"
        "Mean observations per image: 5916.109215\n"
        "Mean reprojection error: 0.940535px\n"
    )
    metrics = parse_model_analyzer_output(text)
    assert metrics["registeredImages"] == 293
    assert metrics["images"] == 293
    assert metrics["points"] == 140050
    assert metrics["observations"] == 1733420
    assert metrics["meanTrackLength"] == 12.377151
    assert metrics["meanObservationsPerImage"] == 5916.109215
    assert metrics["meanReprojectionError"] == 0.940535


def test_parse_real_colmap_model_analyzer_output():
    """The literal glog-formatted lines supplied in the bug report
    (verbatim format, with the timestamp/thread/source fields COLMAP
    actually emits before the '] ' separator)."""
    text = "\n".join([
        "I20260919 09:06:13.687167 12345 model.cc:440] Rigs: 293",
        "I20260919 09:06:13.689742 12345 model.cc:440] Cameras: 293",
        "I20260919 09:06:13.690030 12345 model.cc:440] Frames: 293",
        "I20260919 09:06:13.690222 12345 model.cc:440] Registered frames: 293",
        "I20260919 09:06:13.690387 12345 model.cc:440] Images: 293",
        "I20260919 09:06:13.690509 12345 model.cc:440] Registered images: 293",
        "I20260919 09:06:13.690639 12345 model.cc:440] Points: 140050",
        "I20260919 09:06:13.690706 12345 model.cc:440] Observations: 1733420",
        "I20260919 09:06:13.690780 12345 model.cc:440] Mean track length: 12.377151",
        "I20260919 09:06:13.690847 12345 model.cc:440] Mean observations per image: 5916.109215",
        "I20260919 09:06:13.690895 12345 model.cc:440] Mean reprojection error: 0.940535px",
    ])

    metrics = parse_model_analyzer_output(text)

    assert metrics["totalImages"] == 293
    assert metrics["registeredImages"] == 293
    assert metrics["points"] == 140050
    assert metrics["observations"] == 1733420
    assert metrics["meanTrackLength"] == 12.377151
    assert metrics["meanReprojectionError"] == 0.940535


def test_registration_percentage():
    assert calculate_registration_percentage(293, 293) == 100.0
    assert calculate_registration_percentage(0, 0) == 0.0
    assert round(calculate_registration_percentage(146, 293), 2) == 49.83


def test_parse_model_analyzer_output_malformed_metric_raises():
    with pytest.raises(ColmapParseError):
        parse_model_analyzer_output("Registered images: 12.34.56\n")


def test_parse_model_analyzer_output_malformed_integer_metric_raises():
    # "12.5" is not a valid integer for a metric declared as integer-only.
    with pytest.raises(ColmapParseError):
        parse_model_analyzer_output("Points: 12.5\n")


def _write_cameras_bin(path, cameras: list[tuple[int, int, int, int, list[float]]]) -> None:
    """cameras: list of (camera_id, model_id, width, height, params)."""
    with open(path, "wb") as handle:
        handle.write(struct.pack("<Q", len(cameras)))
        for camera_id, model_id, width, height, params in cameras:
            handle.write(struct.pack("<iiQQ", camera_id, model_id, width, height))
            for value in params:
                handle.write(struct.pack("<d", value))


def test_parse_cameras_bin_simple_radial(tmp_path):
    path = tmp_path / "cameras.bin"
    _write_cameras_bin(path, [(1, 2, 1920, 1080, [1400.0, 960.0, 540.0, -0.05])])

    cameras = parse_cameras_bin(path)

    assert len(cameras) == 1
    camera = cameras[0]
    assert isinstance(camera, CameraModelInfo)
    assert camera.model_name == "SIMPLE_RADIAL"
    assert camera.has_distortion is True
    assert camera.width == 1920
    assert camera.height == 1080


def test_parse_cameras_bin_pinhole_has_no_distortion(tmp_path):
    path = tmp_path / "cameras.bin"
    _write_cameras_bin(path, [(1, 1, 1920, 1080, [1400.0, 1400.0, 960.0, 540.0])])

    cameras = parse_cameras_bin(path)

    assert cameras[0].model_name == "PINHOLE"
    assert cameras[0].has_distortion is False


def test_parse_cameras_bin_multiple_cameras(tmp_path):
    path = tmp_path / "cameras.bin"
    _write_cameras_bin(
        path,
        [
            (1, 2, 1920, 1080, [1400.0, 960.0, 540.0, -0.05]),
            (2, 2, 1920, 1080, [1400.0, 960.0, 540.0, -0.05]),
        ],
    )

    cameras = parse_cameras_bin(path)
    assert len(cameras) == 2
    assert {c.camera_id for c in cameras} == {1, 2}


def test_parse_cameras_bin_truncated_raises(tmp_path):
    path = tmp_path / "cameras.bin"
    path.write_bytes(struct.pack("<Q", 1))  # claims 1 camera, but no header follows

    with pytest.raises(ColmapParseError):
        parse_cameras_bin(path)


def test_parse_cameras_bin_unknown_model_id_raises(tmp_path):
    path = tmp_path / "cameras.bin"
    with open(path, "wb") as handle:
        handle.write(struct.pack("<Q", 1))
        handle.write(struct.pack("<iiQQ", 1, 9999, 1920, 1080))

    with pytest.raises(ColmapParseError):
        parse_cameras_bin(path)


def test_parse_cameras_bin_missing_file_raises(tmp_path):
    with pytest.raises(ColmapParseError):
        parse_cameras_bin(tmp_path / "does_not_exist.bin")
