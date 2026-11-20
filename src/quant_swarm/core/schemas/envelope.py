"""Envelope — the universal wrapper for every message on the bus."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from quant_swarm.core.ids import new_id
from quant_swarm.core.timeutils import utcnow

T = TypeVar("T", bound=BaseModel)

SCHEMA_VERSION = 1


class Envelope(BaseModel):
    """Carries a pydantic payload plus routing/tracing metadata.

    ``trace_id`` threads the whole chain collect -> decide -> order -> fill.
    ``type`` is the payload's class name, kept for routing/debug only —
    consumers should always :meth:`unwrap` into a concrete model.
    """

    msg_id: str = Field(default_factory=lambda: new_id("msg"))
    trace_id: str = Field(default_factory=lambda: new_id("trace"))
    ts: datetime = Field(default_factory=utcnow)
    schema_version: int = SCHEMA_VERSION
    type: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def wrap(cls, payload: BaseModel, *, trace_id: str | None = None) -> Envelope:
        env = cls(type=type(payload).__name__, payload=payload.model_dump(mode="json"))
        if trace_id is not None:
            env.trace_id = trace_id
        return env

    def unwrap(self, model: type[T]) -> T:
        return model.model_validate(self.payload)
