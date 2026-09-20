# Local 3DGS Studio

A free, fully local Windows 11 desktop application for orchestrating the
complete 3D Gaussian Splatting workflow: project setup, image input,
COLMAP reconstruction, LichtFeld Studio training, cleanup, export, and
rendering.

This build implements **Phase 01 (Foundation)**, **Phase 02 (Projects
Setup)**, **Phase 03 (Input & Image Validation)**, **Phase 04 (COLMAP
Integration)**, and **Phase 05 (Reconstruction QC)**, per the current
specification. LichtFeld training, cleanup, export, and rendering are
intentionally not implemented yet.

## Principles

- 100% local. No cloud services, no accounts, no subscription.
- PySide6 / Qt6 only. PyQt5, PyQt6, and PySide2 are never used or mixed in.
- Source data (`rawData/images`, `rawData/videos`) is never automatically
  deleted, moved, renamed, or overwritten.
- All long-running work runs off the GUI thread (`QProcess` + `QThread`);
  the interface never freezes.
- Every path inside a project is resolved through one central
  `ProjectPathResolver` — GUI code never builds paths by hand.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Run

```bash
python run.py
```

## Test

```bash
pytest
```

## Project structure created by "Projects Setup"

```
<projectRoot>\<projectName>
├── project.json
├── rawData
│   ├── images
│   │   └── v01
│   └── videos
├── colmap
│   └── v01
├── export
│   ├── pointCloud
│   └── splats
├── renders
└── logs
```

`project.json` stores `projectRoot` conceptually as the only absolute
path; every other path inside it (`images`, `colmap`, `pointCloudExport`,
etc.) is relative. Moving the whole project folder to a different drive
only requires reopening it from the new location — nothing else breaks.

## Building a Windows executable

```bash
pyinstaller build.spec
```

The resulting executable is written to `dist/Local3DGSStudio/`.

## Source layout

```
src/
├── main.py                 entry point (also see run.py at the repo root)
├── core/                    non-GUI logic
│   ├── project_manager.py       facade: create/open/close/save projects
│   ├── project_structure.py     folder tree creation/validation/repair
│   ├── project_paths.py         ProjectPathResolver (single source of truth)
│   ├── project_json.py          project.json data model + (de)serialization
│   ├── config_manager.py        last_project.json + app settings
│   ├── software_detector.py     COLMAP / LichtFeld / FFmpeg detection
│   ├── process_manager.py       non-blocking QProcess wrapper
│   ├── hardware_monitor.py      GPU / RAM / disk readings
│   ├── input_manager.py         resolves/lists active project images & videos
│   ├── image_validator.py       validation logic + QThread worker
│   └── logger.py                application + per-project logging
├── gui/                      PySide6 widgets
│   ├── main_window.py            sidebar navigation, startup sequence
│   ├── dashboard.py
│   ├── projects_setup.py
│   ├── input_panel.py             Input page (images/videos, new version)
│   ├── image_validation.py        Image Validation page (progress, table, report)
│   ├── settings.py
│   ├── logs.py
│   └── theme.py                  dark QSS stylesheet
└── utils/
    ├── validators.py             project name / version / root validation
    ├── filesystem.py
    ├── image_utils.py            Pillow-based dimension/corruption checks
    ├── hash_utils.py             chunked SHA256 for duplicate detection
    ├── colmap_parser.py          version/metrics regex parsing of COLMAP CLI output
    └── windows_junction.py       mklink /J image junction (symlink fallback off-Windows)
```

## Phase 03: Input & Image Validation

- **Input page** resolves the active version's `rawData/images/vNN` and
  `rawData/videos` directories automatically from `project.json` — you never
  browse for them on an existing project. Shows live image/video counts,
  "Open Image/Video Folder" (Explorer), and "New Version" (scans existing
  version folders, creates the next `vNN` image + COLMAP directories without
  touching or duplicating any previous version).
- **Image Validation page** runs format/corruption/resolution/file-size/
  duplicate-filename/duplicate-content (SHA256) checks on a background
  `QThread`, with a live progress bar, cancel support, summary cards, a
  sortable per-file table, and a JSON report export. Results are written
  back into `project.json` under a new `validation` section. No source file
  is ever modified, moved, or deleted by validation.

## Phase 04: COLMAP Integration

- **COLMAP page** detects the configured `COLMAP.bat`/executable (runs a
  harmless `-h` to confirm it's really COLMAP and parse its version/CUDA
  build), shows a preflight check before anything runs, and drives the
  five-stage pipeline — **Database → Feature Extraction → Feature Matching
  → Mapper → Model Analysis** — either as "Run Full Pipeline" or one step
  at a time.
- Every stage runs through the existing Phase 01 `ManagedProcess`
  (`QProcess`) wrapper, so the GUI never blocks; `.bat` files are launched
  via `cmd.exe /c` on Windows. Live stdout/stderr, the exact resolved
  command (with a copy-to-clipboard button), and cancellation are all
  wired up.
- The `rawData/images/vNN` source folder is never copied — a Windows
  directory junction (`mklink /J`) is created at `colmap/vNN/images`
  instead. An existing valid junction is left alone; a conflicting real
  directory is reported as an error rather than removed automatically.
- A stage is only marked complete when its real output file(s) exist on
  disk (or, for feature extraction/matching, when the process both exited
  0 *and* `database.db` is still present) — never merely because a process
  started. An existing `database.db` or `sparse/` reconstruction is never
  silently overwritten; the user must explicitly confirm replacing it.
- `model_analyzer`'s output is parsed for registered/total images, points,
  observations, mean track length, and mean reprojection error, displayed
  in the GUI, and written into `project.json`'s `colmap` section (state
  reaches `READY` once every image is registered).
- Image-validation status gates the pipeline: `INVALID` blocks it outright;
  `WARNING` (or not-yet-validated) asks for confirmation; `VALID` proceeds
  silently.

## Phase 05: Reconstruction QC

- **Reconstruction QC page** (sidebar: "Reconstruction") sits between
  COLMAP and the future LichtFeld hand-off. It never re-runs COLMAP or
  touches any reconstruction file — it only reads real disk evidence
  (database, image junction, `sparse/0/{cameras,images,points3D}.bin`)
  plus the metrics `COLMAPManager` already parsed and persisted after
  `model_analyzer` (Phase 04), through the `ReconstructionQC` class in
  `src/core/reconstruction_qc.py`. No QC arithmetic lives in the GUI file.
- Reads `cameras.bin` directly (`colmap_parser.parse_cameras_bin`) to
  report camera model names and detect distortion (e.g. `SIMPLE_RADIAL`).
  **Distortion is informational only** — it's surfaced as a warning and
  in `distortedCameraModels`, but per the reference dataset's own
  expected outcome, it never by itself downgrades a fully-registered,
  low-error reconstruction below `READY`.
- States: `NOT_READY` (nothing attempted), `FAILED` (missing/empty
  database, missing sparse-model binaries, invalid image junction, zero
  registered images, or zero points), `WARNING` (partial registration,
  reprojection error above threshold, short mean track length, or a
  metric that never got parsed — never silently treated as zero), and
  `READY`.
- Result is persisted to `project.json`'s `reconstructionQC` section
  (`Refresh QC` button re-evaluates and re-persists); the page also
  auto-refreshes whenever the COLMAP pipeline finishes, via a
  `pipeline_finished` Qt signal on `ColmapPanel` — kept as a signal
  rather than a direct call so `colmap_panel.py` never needs to import
  QC code.
- "Send to LichtFeld" is visible but disabled in this phase — it will be
  wired up in Phase 06, gated on `QCResult.is_ready_for_lichtfeld`
  (`READY` or `WARNING`; `FAILED`/`NOT_READY` block it).

## Architecture revision: no persistent COLMAP image junction

The project structure and COLMAP integration were revised after Phase 05:

- **COLMAP now reads images directly from `rawData/images/vNN`.** The
  earlier `colmap/vNN/images` Windows directory junction has been removed
  entirely — `COLMAPManager` no longer has `images_junction_path()` or
  `ensure_image_junction()`, and `feature_extractor`/`mapper` are invoked
  with `--image_path` pointing straight at the authoritative image
  directory. This decouples COLMAP workspace validation from junction
  creation/detection, which was the root cause of the old "Image junction
  is missing" QC error.
- **`Reconstruction QC`** validates the authoritative image directory
  itself (exists and is non-empty) instead of a junction — shown on the
  QC page as "Image Source" rather than "Image Junction".
- **`lichtFeld/vNN`** is now part of the permanent project structure
  (created at project setup and at every new-version creation, alongside
  `rawData/images/vNN` and `colmap/vNN`), reserved for LichtFeld
  project/training metadata in a future phase. LichtFeld's own COLMAP
  workspace compatibility (if it needs one) will be handled by an
  application-managed *temporary* staging area outside the permanent
  project folder — not implemented yet, since no LichtFeld workflow
  exists in the app until Phase 06.
- `src/utils/windows_junction.py` is kept as a general-purpose utility
  (it may still be useful for that future temporary staging), but nothing
  in the COLMAP pipeline calls it anymore.
