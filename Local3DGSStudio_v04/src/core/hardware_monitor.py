"""System hardware readings for the Dashboard.

RAM/CPU/disk come from ``psutil``, which is cross-platform. NVIDIA GPU/VRAM
detection uses ``nvidia-smi`` when available and degrades gracefully (no
crash, just "not detected") when it is not -- e.g. when developing off the
target Windows/NVIDIA machine.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass
class GpuInfo:
    available: bool = False
    name: str = ""
    vram_total_mb: int = 0
    vram_used_mb: int = 0
    temperature_c: int = 0
    utilization_percent: int = 0


@dataclass
class SystemInfo:
    ram_total_gb: float = 0.0
    ram_used_gb: float = 0.0
    cpu_percent: float = 0.0
    disk_free_gb: float = 0.0
    disk_total_gb: float = 0.0
    gpu: GpuInfo = None  # type: ignore[assignment]


def read_gpu_info() -> GpuInfo:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return GpuInfo(available=False)

    query = "name,memory.total,memory.used,temperature.gpu,utilization.gpu"
    try:
        output = subprocess.check_output(
            [nvidia_smi, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            timeout=3,
        ).decode().strip()
    except (subprocess.SubprocessError, OSError):
        return GpuInfo(available=False)

    if not output:
        return GpuInfo(available=False)

    first_gpu = output.splitlines()[0]
    parts = [p.strip() for p in first_gpu.split(",")]
    if len(parts) < 5:
        return GpuInfo(available=False)

    try:
        return GpuInfo(
            available=True,
            name=parts[0],
            vram_total_mb=int(float(parts[1])),
            vram_used_mb=int(float(parts[2])),
            temperature_c=int(float(parts[3])),
            utilization_percent=int(float(parts[4])),
        )
    except ValueError:
        return GpuInfo(available=False)


def read_system_info(disk_path: Path | None = None) -> SystemInfo:
    virtual_mem = psutil.virtual_memory()
    disk_target = disk_path if disk_path is not None else Path.cwd().anchor or "/"
    try:
        disk = psutil.disk_usage(str(disk_target))
        disk_free_gb = disk.free / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)
    except OSError:
        disk_free_gb = 0.0
        disk_total_gb = 0.0

    return SystemInfo(
        ram_total_gb=virtual_mem.total / (1024 ** 3),
        ram_used_gb=(virtual_mem.total - virtual_mem.available) / (1024 ** 3),
        cpu_percent=psutil.cpu_percent(interval=None),
        disk_free_gb=disk_free_gb,
        disk_total_gb=disk_total_gb,
        gpu=read_gpu_info(),
    )
