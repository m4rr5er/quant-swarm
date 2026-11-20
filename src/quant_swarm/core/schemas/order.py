"""Order & fill contracts between the brain, risk layer and execution agent."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from quant_swarm.core.ids import new_id
from quant_swarm.core.schemas.envelope import SCHEMA_VERSION
from quant_swarm.core.timeutils import utcnow


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TIF(StrEnum):
    DAY = "DAY"
    IOC = "IOC"
    GTC = "GTC"


class OrderIntent(BaseModel):
    schema_version: int = SCHEMA_VERSION
    order_id: str = Field(default_factory=lambda: new_id("ord"))
    ts: datetime = Field(default_factory=utcnow)
    decision_id: str
    symbol: str
    side: Side
    qty: int = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = Field(default=None, gt=0)
    tif: TIF = TIF.DAY

    @model_validator(mode="after")
    def _limit_needs_price(self) -> OrderIntent:
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT order requires limit_price")
        return self


class FillStatus(StrEnum):
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"


class FillReport(BaseModel):
    schema_version: int = SCHEMA_VERSION
    fill_id: str = Field(default_factory=lambda: new_id("fill"))
    order_id: str
    status: FillStatus
    filled_qty: int = Field(ge=0)
    avg_price: float = Field(ge=0.0)
    ts: datetime = Field(default_factory=utcnow)
    broker: str = "paper"
    meta: dict[str, Any] = Field(default_factory=dict)
