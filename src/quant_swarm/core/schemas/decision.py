"""Decision — the single decision outlet's output."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from quant_swarm.core.ids import new_id
from quant_swarm.core.schemas.envelope import SCHEMA_VERSION
from quant_swarm.core.timeutils import utcnow


class Action(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    ADD = "ADD"
    REDUCE = "REDUCE"
    HOLD = "HOLD"


class Decision(BaseModel):
    """A trading decision emitted by the AI brain.

    ``card_refs`` links the decision back to the InfoCards that motivated it,
    which keeps every call auditable.
    """

    schema_version: int = SCHEMA_VERSION
    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    ts: datetime = Field(default_factory=utcnow)
    symbol: str
    action: Action
    target_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    qty: int | None = Field(default=None, gt=0)
    horizon: str | None = None
    rationale: str = ""
    card_refs: list[str] = Field(default_factory=list)
    llm: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _size_required_for_trades(self) -> Decision:
        if self.action is not Action.HOLD and self.target_weight is None and self.qty is None:
            raise ValueError("non-HOLD decision requires target_weight or qty")
        return self
