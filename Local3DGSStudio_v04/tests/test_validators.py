import pytest

from src.utils.validators import (
    ValidationError,
    next_version_string,
    validate_project_name,
    validate_project_root,
    validate_version,
)


def test_valid_project_name_passes():
    assert validate_project_name("gsOfficeBuildingPillar") == "gsOfficeBuildingPillar"


@pytest.mark.parametrize(
    "bad_name",
    ["", "   ", "My Project", "gs office", "gs/office", "gs:office", "GsOffice", "CON", "com1"],
)
def test_invalid_project_names_raise(bad_name):
    with pytest.raises(ValidationError):
        validate_project_name(bad_name)


def test_valid_version_passes():
    assert validate_version("v01") == "v01"


@pytest.mark.parametrize("bad_version", ["", "v1", "version01", "v001", "V01", "v1a"])
def test_invalid_versions_raise(bad_version):
    with pytest.raises(ValidationError):
        validate_version(bad_version)


def test_next_version_string_increments():
    assert next_version_string("v01") == "v02"
    assert next_version_string("v09") == "v10"


def test_project_root_must_be_absolute():
    with pytest.raises(ValidationError):
        validate_project_root("relative/path")


def test_project_root_empty_raises():
    with pytest.raises(ValidationError):
        validate_project_root("")
