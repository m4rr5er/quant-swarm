"""MessageBus abstraction + implementations (NATS for real runs, local for tests)."""

from quant_swarm.core.bus.base import BusMessage, Handler, MessageBus, Subscription
from quant_swarm.core.bus.local_bus import LocalBus

__all__ = ["BusMessage", "Handler", "LocalBus", "MessageBus", "Subscription"]


def make_bus(kind: str, url: str) -> MessageBus:
    """Factory — ``kind`` is ``nats`` or ``local`` (settings.bus)."""
    if kind == "local":
        return LocalBus()
    if kind == "nats":
        from quant_swarm.core.bus.nats_bus import NatsBus

        return NatsBus(url)
    raise ValueError(f"unknown bus kind: {kind!r}")
