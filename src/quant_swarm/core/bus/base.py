"""Message-bus contract — mirrors NATS semantics so implementations stay swappable."""

from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from quant_swarm.core.schemas.envelope import Envelope


class BusMessage:
    """One delivered message. Handlers answer a request via :meth:`respond`."""

    __slots__ = ("_responder", "data", "reply", "subject")

    def __init__(
        self,
        subject: str,
        data: bytes,
        reply: str | None = None,
        responder: Callable[[bytes], Awaitable[None]] | None = None,
    ) -> None:
        self.subject = subject
        self.data = data
        self.reply = reply
        self._responder = responder

    def envelope(self) -> Envelope:
        return Envelope.model_validate_json(self.data)

    async def respond(self, data: bytes) -> None:
        """Publish ``data`` to the reply inbox (no-op for plain publishes)."""
        if self._responder is not None:
            await self._responder(data)


class Subscription(abc.ABC):
    subject: str

    @abc.abstractmethod
    async def unsubscribe(self) -> None:
        """Stop delivery and release the subscription."""


Handler = Callable[[BusMessage], Awaitable[None]]


class MessageBus(abc.ABC):
    """Pub/sub + request/reply + queue groups — the bus knows bytes only.

    The wire format is always an :class:`Envelope` JSON document; use
    :meth:`publish_model` / :meth:`request_model` for typed payloads.
    """

    name: str = "abstract"

    async def connect(self) -> None:  # noqa: B027 — intentional optional hook
        """Startup hook — no-op for implementations without a server."""

    @abc.abstractmethod
    async def publish(self, subject: str, data: bytes) -> None: ...

    async def publish_model(
        self, subject: str, model: BaseModel, *, trace_id: str | None = None
    ) -> Envelope:
        """Wrap ``model`` in an Envelope, publish, return the envelope."""
        env = Envelope.wrap(model, trace_id=trace_id)
        await self.publish(subject, env.model_dump_json().encode())
        return env

    @abc.abstractmethod
    async def subscribe(
        self,
        subject: str,
        handler: Handler,
        *,
        queue_group: str | None = None,
        durable: str | None = None,
    ) -> Subscription:
        """``durable`` names a persistent consumer on JetStream-backed buses;
        ignored elsewhere (restart resumes where the durable left off)."""

    @abc.abstractmethod
    async def request(self, subject: str, data: bytes, *, timeout: float = 5.0) -> bytes: ...

    async def request_model(
        self, subject: str, model: BaseModel, *, timeout: float = 5.0
    ) -> Envelope:
        env = Envelope.wrap(model)
        raw = await self.request(subject, env.model_dump_json().encode(), timeout=timeout)
        return Envelope.model_validate_json(raw)

    async def close(self) -> None:  # noqa: B027 — intentional optional hook
        ...

    async def __aenter__(self) -> MessageBus:
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
