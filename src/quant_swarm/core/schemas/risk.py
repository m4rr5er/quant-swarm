"""Risk events & liveness contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from quant_swarm.core.ids import new_id
from quant_swarm.core.schemas.envelope import SCHEMA_VERSION
from quant_swarm.core.timeutils import utcnow


class RiskLevel(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


class RiskEvent(BaseModel):
    """Anomaly/risk signal from the event monitor or risk-review agents.

    ``veto=True`` on a CRITICAL event tells the execution path to block
    pending orders within ``scope`` until cleared.
    """

    schema_version: int = SCHEMA_VERSION
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    ts: datetime = Field(default_factory=utcnow)
    level: RiskLevel
    code: str
    message: str = ""
    scope: str = "global"
    symbols: list[str] = Field(default_factory=list)
    veto: bool = False
    source: str = ""


class AgentState(StrEnum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    DEAD = "DEAD"


class Heartbeat(BaseModel):
    schema_version: int = SCHEMA_VERSION
    agent: str
    ts: datetime = Field(default_factory=utcnow)
    state: AgentState = AgentState.RUNNING
    metrics: dict[str, Any] = Field(default_factory=dict)
