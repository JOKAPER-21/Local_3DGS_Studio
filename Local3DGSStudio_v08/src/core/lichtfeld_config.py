"""LichtFeld Studio configuration: where its executable lives."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LichtFeldConfig:
    executable_path: str = ""
