"""InfoCard — the only output format of every collection agent."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from quant_swarm.core.ids import new_id
from quant_swarm.core.schemas.envelope import SCHEMA_VERSION


class CardKind(StrEnum):
    MARKET = "market"
    FUNDAMENTAL = "fundamental"
    CAPITAL = "capital"
    EVENT = "event"


class InfoCard(BaseModel):
    """Standardized fact produced by a collection agent.

    Outer fields are fixed for every agent; the inner ``payload`` is free-form
    and defined per producer (e.g. OHLCV + indicators for market cards).
    """

    schema_version: int = SCHEMA_VERSION
    card_id: str = Field(default_factory=lambda: new_id("card"))
    agent: str
    kind: CardKind
    symbols: list[str] = Field(default_factory=list)
    asof: datetime
    ttl_sec: int = Field(default=3600, ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
