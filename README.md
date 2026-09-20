# 3DGS Projects Workspace

This repository contains the source code and experiment projects for **Local 3DGS Studio**, a local Windows desktop application for managing a 3D Gaussian Splatting workflow.

The workspace includes several application iterations (`Local3DGSStudio_v01` through `Local3DGSStudio_v10`) and dated reconstruction projects used for testing COLMAP, LichtFeld Studio, image capture, export, and rendering workflows.

## Repository Contents

- `Local3DGSStudio_v10/` - newest application iteration and the recommended starting point
- `Local3DGSStudio_v01/` through `Local3DGSStudio_v09/` - earlier application iterations
- `Local_3DGS_Studio/` - standalone project repository and documentation
- `260917_l3dgssTest01/` through `260919_skdp_plantA/` - dated reconstruction projects
- `install_dependencies.bat` - Windows dependency installation helper

Each application iteration generally contains:

```text
run.py
requirements.txt
src/
tests/
build.spec
```

## Features

Local 3DGS Studio is designed to provide a local project workflow for:

- Creating and opening reconstruction projects
- Validating project names, paths, and input images
- Organizing raw images and videos
- Preparing COLMAP and LichtFeld Studio workflows
- Monitoring processes and hardware resources
- Reviewing logs and project state
- Exporting and rendering trained Gaussian splats, where implemented by the selected version

The application is designed for Windows and uses PySide6/Qt6 for its desktop interface.

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer recommended
- COLMAP and LichtFeld Studio for reconstruction and training stages
- A suitable GPU for practical 3D Gaussian Splatting training

Python dependencies for the current v10 application are listed in `Local3DGSStudio_v10/requirements.txt`.

## Setup

Open PowerShell in the repository root and create an environment for the application version you want to run:

```powershell
Set-Location .\Local3DGSStudio_v10
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The repository also includes a convenience installer for the main Python packages:

```powershell
Set-Location C:\Projects_3dgs
.\install_dependencies.bat
```

## Run

From the selected application directory:

```powershell
python run.py
```

For the current recommended version:

```powershell
Set-Location .\Local3DGSStudio_v10
python run.py
```

## Test

Run the tests from the selected application directory:

```powershell
pytest
```

## Build A Windows Executable

The application versions include a PyInstaller specification:

```powershell
pyinstaller build.spec
```

The generated build is written to the version's `dist/` directory.

## Project Data Layout

A managed reconstruction project typically contains:

```text
projectName/
├── project.json
├── rawData/
│   ├── images/
│   └── videos/
├── colmap/
├── export/
├── renders/
└── logs/
```

`project.json` stores project metadata and relative paths. The large folders contain captured source media, COLMAP databases, trained models, renders, and logs.

## Git And Large Files

Large generated and captured files are intentionally excluded from this repository through the root `.gitignore`. This includes raw media, COLMAP data, trained model exports, renders, logs, ZIP archives, and other large binary artifacts.

Keep those files locally with the corresponding project folder. Only source code, project metadata, tests, configuration, and documentation are intended to be published here.

## Development Notes

The version directories are preserved to make changes between application iterations easy to compare. New development should normally begin in `Local3DGSStudio_v10` unless a specific earlier version is being maintained or tested.
