from pathlib import Path

from src.core.reconstruction_state import (
    STATE_ANALYZED,
    STATE_DATABASE_CREATED,
    STATE_FEATURES_EXTRACTED,
    STATE_FEATURES_MATCHED,
    STATE_NOT_STARTED,
    STATE_READY,
    STATE_SPARSE_RECONSTRUCTION_CREATED,
    derive_reconstruction_state,
)


def _empty_colmap_info() -> dict:
    return {
        "featureExtraction": {"completed": False},
        "featureMatching": {"completed": False},
        "analysis": {"completed": False},
    }


def test_not_started_when_nothing_exists(tmp_path: Path):
    state = derive_reconstruction_state(
        tmp_path / "database.db", tmp_path / "sparse" / "0", _empty_colmap_info()
    )
    assert state.state == STATE_NOT_STARTED
    assert not state.database_created


def test_database_created_when_file_exists(tmp_path: Path):
    db = tmp_path / "database.db"
    db.write_bytes(b"sqlite content")
    state = derive_reconstruction_state(db, tmp_path / "sparse" / "0", _empty_colmap_info())
    assert state.database_created
    assert state.state == STATE_DATABASE_CREATED


def test_zero_byte_database_is_not_considered_created(tmp_path: Path):
    db = tmp_path / "database.db"
    db.write_bytes(b"")
    state = derive_reconstruction_state(db, tmp_path / "sparse" / "0", _empty_colmap_info())
    assert not state.database_created
    assert state.state == STATE_NOT_STARTED


def test_features_extracted_requires_database_and_flag(tmp_path: Path):
    db = tmp_path / "database.db"
    db.write_bytes(b"data")
    info = _empty_colmap_info()
    info["featureExtraction"]["completed"] = True
    state = derive_reconstruction_state(db, tmp_path / "sparse" / "0", info)
    assert state.features_extracted
    assert state.state == STATE_FEATURES_EXTRACTED


def test_features_matched_requires_extraction_flag_too(tmp_path: Path):
    db = tmp_path / "database.db"
    db.write_bytes(b"data")
    info = _empty_colmap_info()
    info["featureMatching"]["completed"] = True  # extraction flag NOT set
    state = derive_reconstruction_state(db, tmp_path / "sparse" / "0", info)
    assert not state.features_matched
    assert state.state == STATE_DATABASE_CREATED


def test_mapper_completed_derived_from_actual_sparse_files(tmp_path: Path):
    db = tmp_path / "database.db"
    db.write_bytes(b"data")
    sparse_model = tmp_path / "sparse" / "0"
    sparse_model.mkdir(parents=True)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        (sparse_model / name).write_bytes(b"x")

    info = _empty_colmap_info()
    info["featureExtraction"]["completed"] = True
    info["featureMatching"]["completed"] = True
    state = derive_reconstruction_state(db, sparse_model, info)

    assert state.mapper_completed
    assert state.state == STATE_SPARSE_RECONSTRUCTION_CREATED


def test_mapper_not_completed_if_a_required_file_is_missing(tmp_path: Path):
    sparse_model = tmp_path / "sparse" / "0"
    sparse_model.mkdir(parents=True)
    (sparse_model / "cameras.bin").write_bytes(b"x")
    (sparse_model / "images.bin").write_bytes(b"x")
    # points3D.bin missing

    state = derive_reconstruction_state(
        tmp_path / "database.db", sparse_model, _empty_colmap_info()
    )
    assert not state.mapper_completed


def test_analyzed_state(tmp_path: Path):
    db = tmp_path / "database.db"
    db.write_bytes(b"data")
    sparse_model = tmp_path / "sparse" / "0"
    sparse_model.mkdir(parents=True)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        (sparse_model / name).write_bytes(b"x")

    info = _empty_colmap_info()
    info["featureExtraction"]["completed"] = True
    info["featureMatching"]["completed"] = True
    info["analysis"] = {"completed": True, "totalImages": 293, "registeredImages": 200}

    state = derive_reconstruction_state(db, sparse_model, info)
    assert state.analysis_completed
    assert state.state == STATE_ANALYZED  # not fully registered


def test_ready_state_when_all_images_registered(tmp_path: Path):
    db = tmp_path / "database.db"
    db.write_bytes(b"data")
    sparse_model = tmp_path / "sparse" / "0"
    sparse_model.mkdir(parents=True)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        (sparse_model / name).write_bytes(b"x")

    info = _empty_colmap_info()
    info["featureExtraction"]["completed"] = True
    info["featureMatching"]["completed"] = True
    info["analysis"] = {"completed": True, "totalImages": 293, "registeredImages": 293}

    state = derive_reconstruction_state(db, sparse_model, info)
    assert state.state == STATE_READY
