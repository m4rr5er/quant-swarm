"""Shared filesystem locations (persona files etc.)."""

from __future__ import annotations

from pathlib import Path

from quant_swarm.core.config import PROJECT_ROOT

PERSONA_DIR = PROJECT_ROOT / "persona"


def persona_path(name: str) -> Path:
    return PERSONA_DIR / f"{name}.md"
