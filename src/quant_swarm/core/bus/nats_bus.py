"""NATS-backed bus (nats-py).

Two modes behind the same contract:
- Core NATS (``jetstream=False``): plain pub/sub + request/reply.
- JetStream (``jetstream=True``): a ``QS`` stream over ``qs.>``, publishes
  carry ``Nats-Msg-Id`` for server-side dedup, subscriptions become named
  durable consumers (``deliver_policy=new``) — a restarted process resumes
  where its durable left off instead of losing the gap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from quant_swarm.core.schemas.envelope import Envelope

from .base import BusMessage, Handler, MessageBus, Subscription

if TYPE_CHECKING:
    from nats.aio.client import Client as NatsClient
    from nats.aio.subscription import Subscription as NatsSubscription
    from nats.js import JetStreamContext

STREAM = "QS"


class _NatsSub(Subscription):
    def __init__(self, sub: NatsSubscription, pattern: str) -> None:
        self._sub = sub
        self.subject = pattern

    async def unsubscribe(self) -> None:
        await self._sub.unsubscribe()


class NatsBus(MessageBus):
    name = "nats"

    def __init__(
        self, url: str = "nats://127.0.0.1:4222", *, jetstream: bool = False
    ) -> None:
        self._url = url
        self._use_js = jetstream
        self._nc: NatsClient | None = None
        self._js: JetStreamContext | None = None

    async def connect(self) -> None:
        import nats

        self._nc = await nats.connect(self._url)
        if not self._use_js:
            return
        try:
            self._js = self._nc.jetstream()
            try:
                await self._js.add_stream(name=STREAM, subjects=["qs.>"])
                logger.info("jetstream: stream {} ready (qs.>)", STREAM)
            except Exception as exc:
                if "already in use" in str(exc) or "stream name" in str(exc):
                    logger.info("jetstream: stream {} exists", STREAM)
                else:
                    raise
        except Exception as exc:
            logger.warning(
                "jetstream unavailable ({}); falling back to core NATS — "
                "start the server with -js for durability",
                exc,
            )
            self._js = None

    async def publish(self, subject: str, data: bytes) -> None:
        if self._js is not None:
            # Nats-Msg-Id lets the stream dedupe retries on the same envelope.
            try:
                msg_id = Envelope.model_validate_json(data).msg_id
            except Exception:
                msg_id = None
            await self._js.publish(
                subject, data, headers={"Nats-Msg-Id": msg_id} if msg_id else None
            )
            return
        await self._client().publish(subject, data)

    async def subscribe(
        self,
        subject: str,
        handler: Handler,
        *,
        queue_group: str | None = None,
        durable: str | None = None,
    ) -> Subscription:
        nc = self._client()

        async def _wrapped(nats_msg) -> None:
            reply = nats_msg.reply or None

            async def _responder(payload: bytes) -> None:
                if reply:
                    await nc.publish(reply, payload)

            await handler(BusMessage(nats_msg.subject, nats_msg.data, reply, _responder))

        if self._js is not None and durable:
            sub = await self._js.subscribe(
                subject,
                queue=queue_group or "",
                cb=_wrapped,
                durable=durable,
                deliver_policy="new",
            )
        else:
            sub = await nc.subscribe(subject, queue=queue_group or "", cb=_wrapped)
        return _NatsSub(sub, subject)

    async def request(self, subject: str, data: bytes, *, timeout: float = 5.0) -> bytes:
        resp = await self._client().request(subject, data, timeout=timeout)
        return resp.data

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
            self._js = None

    def _client(self) -> NatsClient:
        if self._nc is None or not self._nc.is_connected:
            raise RuntimeError("NatsBus.connect() has not been called (or connection dropped)")
        return self._nc

