# Local 3DGS Studio

A free, fully local Windows 11 desktop application for orchestrating the
complete 3D Gaussian Splatting workflow: project setup, image input,
COLMAP reconstruction, LichtFeld Studio training, cleanup, export, and
rendering.

This build implements **Phase 01 (Foundation)** and **Phase 02 (Projects
Setup)** only, per the current specification. COLMAP execution, LichtFeld
training, cleanup, export, and rendering are intentionally not implemented
yet.

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
│   └── logger.py                application + per-project logging
├── gui/                      PySide6 widgets
│   ├── main_window.py            sidebar navigation, startup sequence
│   ├── dashboard.py
│   ├── projects_setup.py
│   ├── settings.py
│   ├── logs.py
│   └── theme.py                  dark QSS stylesheet
└── utils/
    ├── validators.py             project name / version / root validation
    └── filesystem.py
```
