"""In-process bus for tests and all-in-one dev mode.

Delivery is inline and deterministic (``publish`` awaits each handler) so
tests need no sleeps. A crashing handler is logged and skipped — a broken
consumer must never take the bus down.
"""

from __future__ import annotations

import asyncio
import itertools
import uuid

from loguru import logger

from quant_swarm.core.subjects import match_subject

from .base import BusMessage, Handler, MessageBus, Subscription


class _Sub(Subscription):
    def __init__(
        self,
        bus: LocalBus,
        pattern: str,
        handler: Handler,
        queue_group: str | None,
    ) -> None:
        self._bus = bus
        self.subject = pattern
        self.handler = handler
        self.queue_group = queue_group
        self.active = True

    async def unsubscribe(self) -> None:
        self.active = False
        self._bus._subs = [s for s in self._bus._subs if s.active]


class LocalBus(MessageBus):
    name = "local"

    def __init__(self) -> None:
        self._subs: list[_Sub] = []
        self._rr: dict[str, itertools.count] = {}
        self._closed = False

    async def publish(self, subject: str, data: bytes) -> None:
        self._check()
        for sub in self._targets(subject):
            try:
                await sub.handler(BusMessage(subject, data))
            except Exception:
                logger.exception("local bus handler crashed on {}", subject)

    async def subscribe(
        self,
        subject: str,
        handler: Handler,
        *,
        queue_group: str | None = None,
        durable: str | None = None,
    ) -> Subscription:
        self._check()
        sub = _Sub(self, subject, handler, queue_group)
        self._subs.append(sub)
        return sub

    async def request(self, subject: str, data: bytes, *, timeout: float = 5.0) -> bytes:
        self._check()
        inbox = f"_INBOX.{uuid.uuid4().hex}"
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bytes] = loop.create_future()

        async def _once(msg: BusMessage) -> None:
            if not fut.done():
                fut.set_result(msg.data)

        inbox_sub = await self.subscribe(inbox, _once)
        try:
            targets = self._targets(subject)
            if not targets:
                raise TimeoutError(f"no responders subscribed to {subject!r}")

            async def _responder(payload: bytes) -> None:
                await self.publish(inbox, payload)

            # NATS request semantics: exactly one responder gets the message.
            msg = BusMessage(subject, data, reply=inbox, responder=_responder)
            try:
                await targets[0].handler(msg)
            except Exception:
                logger.exception("local bus responder crashed on {}", subject)
            return await asyncio.wait_for(fut, timeout)
        finally:
            await inbox_sub.unsubscribe()

    async def close(self) -> None:
        self._subs.clear()
        self._closed = True

    def _check(self) -> None:
        if self._closed:
            raise RuntimeError("LocalBus is closed")

    def _targets(self, subject: str) -> list[_Sub]:
        """All matching subs; queue groups contribute one member each (round-robin)."""
        out: list[_Sub] = []
        groups: dict[str, list[_Sub]] = {}
        for s in self._subs:
            if not s.active or not match_subject(s.subject, subject):
                continue
            if s.queue_group is None:
                out.append(s)
            else:
                groups.setdefault(s.queue_group, []).append(s)
        for group, members in groups.items():
            idx = next(self._rr.setdefault(group, itertools.count())) % len(members)
            out.append(members[idx])
        return out
