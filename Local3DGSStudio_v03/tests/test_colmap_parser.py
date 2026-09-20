from src.utils.colmap_parser import (
    calculate_registration_percentage,
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


def test_registration_percentage():
    assert calculate_registration_percentage(293, 293) == 100.0
    assert calculate_registration_percentage(0, 0) == 0.0
    assert round(calculate_registration_percentage(146, 293), 2) == 49.83
