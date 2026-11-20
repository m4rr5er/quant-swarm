"""MessageBus abstraction + implementations (NATS for real runs, local for tests)."""

from quant_swarm.core.bus.base import BusMessage, Handler, MessageBus, Subscription
from quant_swarm.core.bus.local_bus import LocalBus

__all__ = ["BusMessage", "Handler", "LocalBus", "MessageBus", "Subscription"]


def make_bus(kind: str, url: str) -> MessageBus:
    """Factory — ``kind`` is ``nats``, ``nats_js`` (JetStream) or ``local``."""
    if kind == "local":
        return LocalBus()
    if kind in ("nats", "nats_js"):
        from quant_swarm.core.bus.nats_bus import NatsBus

        return NatsBus(url, jetstream=kind == "nats_js")
    raise ValueError(f"unknown bus kind: {kind!r}")
