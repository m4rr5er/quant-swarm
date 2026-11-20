"""Shared filesystem locations (persona files etc.)."""

from __future__ import annotations

from pathlib import Path

from quant_swarm.core.config import PROJECT_ROOT

PERSONA_DIR = PROJECT_ROOT / "persona"
SKILLS_DIR = PROJECT_ROOT / "skills"


def persona_path(name: str) -> Path:
    return PERSONA_DIR / f"{name}.md"


def skill_dir(agent: str) -> Path:
    return SKILLS_DIR / agent
