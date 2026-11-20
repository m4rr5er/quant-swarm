"""Chat & orchestration contracts — user <-> router <-> experts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from quant_swarm.core.ids import new_id
from quant_swarm.core.schemas.envelope import SCHEMA_VERSION
from quant_swarm.core.timeutils import utcnow


class ChatRole(StrEnum):
    USER = "user"
    EXPERT = "expert"
    SYSTEM = "system"


class ChatChannel(StrEnum):
    DASHBOARD = "dashboard"
    TELEGRAM = "telegram"


class ChatMessage(BaseModel):
    """One chat turn, on ``qs.chat.in`` (user) or ``qs.chat.out.<chan>``."""

    schema_version: int = SCHEMA_VERSION
    session_id: str = Field(default_factory=lambda: new_id("sess"))
    role: ChatRole = ChatRole.USER
    expert: str | None = None
    channel: ChatChannel = ChatChannel.DASHBOARD
    content: str = ""
    refs: list[str] = Field(default_factory=list)  # card/decision ids for provenance
    ts: datetime = Field(default_factory=utcnow)


class ExpertTask(BaseModel):
    """Router -> expert, on ``qs.expert.<name>``."""

    schema_version: int = SCHEMA_VERSION
    task_id: str = Field(default_factory=lambda: new_id("task"))
    session_id: str
    channel: ChatChannel = ChatChannel.DASHBOARD
    task: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)


class ReviewReport(BaseModel):
    """Learner-produced learning report (M5c; schema frozen now)."""

    schema_version: int = SCHEMA_VERSION
    report_id: str = Field(default_factory=lambda: new_id("rep"))
    agent: str = ""  # "" = system-wide
    kind: str = "observation"  # observation | memory_update | skill_proposal
    summary: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)
