"""CtrlCommand — scheduler -> component control messages."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from quant_swarm.core.schemas.envelope import SCHEMA_VERSION


class CtrlCommand(BaseModel):
    """E.g. ``{"command": "collect"}`` on ``qs.ctrl.collect.<agent>``."""

    schema_version: int = SCHEMA_VERSION
    command: str
    args: dict[str, Any] = Field(default_factory=dict)
