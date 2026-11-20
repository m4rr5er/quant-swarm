"""NATS-backed bus (nats-py).

Core NATS gives pub/sub + request/reply + queue groups. JetStream streams
(persistence/replay/dedup) layer on in M4 — the contract here stays the same.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BusMessage, Handler, MessageBus, Subscription

if TYPE_CHECKING:
    from nats.aio.client import Client as NatsClient
    from nats.aio.subscription import Subscription as NatsSubscription


class _NatsSub(Subscription):
    def __init__(self, sub: NatsSubscription, pattern: str) -> None:
        self._sub = sub
        self.subject = pattern

    async def unsubscribe(self) -> None:
        await self._sub.unsubscribe()


class NatsBus(MessageBus):
    name = "nats"

    def __init__(self, url: str = "nats://127.0.0.1:4222") -> None:
        self._url = url
        self._nc: NatsClient | None = None

    async def connect(self) -> None:
        import nats

        self._nc = await nats.connect(self._url)

    async def publish(self, subject: str, data: bytes) -> None:
        await self._client().publish(subject, data)

    async def subscribe(
        self, subject: str, handler: Handler, *, queue_group: str | None = None
    ) -> Subscription:
        nc = self._client()

        async def _wrapped(nats_msg) -> None:
            reply = nats_msg.reply or None

            async def _responder(payload: bytes) -> None:
                if reply:
                    await nc.publish(reply, payload)

            await handler(BusMessage(nats_msg.subject, nats_msg.data, reply, _responder))

        sub = await nc.subscribe(subject, queue=queue_group or "", cb=_wrapped)
        return _NatsSub(sub, subject)

    async def request(self, subject: str, data: bytes, *, timeout: float = 5.0) -> bytes:
        resp = await self._client().request(subject, data, timeout=timeout)
        return resp.data

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None

    def _client(self) -> NatsClient:
        if self._nc is None or not self._nc.is_connected:
            raise RuntimeError("NatsBus.connect() has not been called (or connection dropped)")
        return self._nc
