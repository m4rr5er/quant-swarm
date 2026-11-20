"""AgentBase — shared lifecycle for every agent process.

Subclasses implement ``on_start``/``on_stop`` and their message handlers.
The base provides: bus subscription bookkeeping, a heartbeat loop on
``qs.heartbeat.<name>``, a per-agent db session factory and a metric counter
surfaced in heartbeats.
"""

from __future__ import annotations

import asyncio
from abc import ABC
from typing import Any

from loguru import logger

from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, Handler, MessageBus, Subscription
from quant_swarm.core.config import AgentSpec, AppConfig, Settings
from quant_swarm.core.db.engine import session_factory
from quant_swarm.core.db.models import InfoCardRow
from quant_swarm.core.schemas import AgentState, Heartbeat, InfoCard
from quant_swarm.core.timeutils import utcnow


class AgentBase(ABC):  # noqa: B024 — hooks are optional, not abstract
    name: str = "agent"
    heartbeat_interval_sec: float = 10.0

    def __init__(self, bus: MessageBus, settings: Settings, cfg: AppConfig) -> None:
        self.bus = bus
        self.settings = settings
        self.cfg = cfg
        self.spec: AgentSpec = cfg.agent(self.name)
        self.sessions = session_factory(settings.db_path)
        self._stop = asyncio.Event()
        self._hb_task: asyncio.Task | None = None
        self._subs: list[Subscription] = []
        self._metrics: dict[str, Any] = {"errors": 0}
        self._seen_ids: set[str] = set()

    async def start(self) -> None:
        await self.on_start()
        self._hb_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("{} started", self.name)

    async def run(self) -> None:
        await self.start()
        await self.wait_stopped()

    async def wait_stopped(self) -> None:
        await self._stop.wait()

    async def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        await self._emit_state(AgentState.STOPPING)
        for sub in self._subs:
            await sub.unsubscribe()
        self._subs.clear()
        if self._hb_task is not None:
            self._hb_task.cancel()
            self._hb_task = None
        await self.on_stop()
        logger.info("{} stopped", self.name)

    async def subscribe(
        self,
        subject: str,
        handler: Handler,
        *,
        queue_group: str | None = None,
        durable: str | None = None,
    ) -> Subscription:
        """Subscribe with M4 hardening: msg_id dedup + handler exceptions -> DLQ."""
        if durable is None:
            durable = f"{self.name}-" + (
                subject.replace(f"{subjects.PREFIX}.", "")
                .replace(".", "_")
                .replace("*", "x")
                .replace(">", "all")
            )

        async def _guarded(msg: BusMessage) -> None:
            try:
                env = msg.envelope()
            except Exception:
                await self._dead_letter(msg, "malformed envelope")
                return
            if env.msg_id in self._seen_ids:
                self.bump("deduped")
                return
            self._remember(env.msg_id)
            try:
                await handler(msg)
            except Exception as exc:
                self.bump("errors")
                logger.bind(trace_id=env.trace_id).exception(
                    "{} handler failed on {}", self.name, subject
                )
                await self._dead_letter(msg, f"{type(exc).__name__}: {exc}")

        sub = await self.bus.subscribe(
            subject, _guarded, queue_group=queue_group, durable=durable
        )
        self._subs.append(sub)
        return sub

    def _remember(self, msg_id: str) -> None:
        self._seen_ids.add(msg_id)
        if len(self._seen_ids) > 20_000:
            self._seen_ids = set(list(self._seen_ids)[-10_000:])

    async def _dead_letter(self, msg: BusMessage, error: str) -> None:
        """Route a failed message to qs.dlq.<agent> + the dead_letters table."""
        from quant_swarm.core.db.models import DLQRow

        try:
            env = msg.envelope()
            payload, msg_id, trace = env.payload, env.msg_id, env.trace_id
        except Exception:
            payload, msg_id, trace = (
                {"raw": msg.data[:4096].decode("utf-8", "replace")},
                "",
                "",
            )
        try:
            async with self.sessions() as s:
                s.add(
                    DLQRow(
                        agent=self.name,
                        subject=msg.subject,
                        msg_id=msg_id,
                        trace_id=trace,
                        error=error[:500],
                        payload=payload if isinstance(payload, dict) else {"data": payload},
                        ts=utcnow(),
                    )
                )
                await s.commit()
            await self.bus.publish(subjects.dlq(self.name), msg.data)
            self.bump("dlq")
        except Exception:
            logger.exception("dead-letter write failed for {}", self.name)

    @property
    def bound(self):
        """Logger pre-bound with the agent name."""
        return logger.bind(agent=self.name)

    def bump(self, key: str, n: int = 1) -> None:
        self._metrics[key] = self._metrics.get(key, 0) + n

    async def persist_card(self, card: InfoCard, trace: str) -> None:
        """Write an InfoCard to info_cards — shared by all collection agents."""
        row = InfoCardRow(
            card_id=card.card_id,
            agent=card.agent,
            kind=str(card.kind),
            symbols=card.symbols,
            asof=card.asof,
            received_ts=utcnow(),
            ttl_sec=card.ttl_sec,
            confidence=card.confidence,
            source=card.source,
            payload=card.payload,
            trace_id=trace,
        )
        async with self.sessions() as s:
            s.add(row)
            await s.commit()

    async def _heartbeat_loop(self) -> None:
        while True:
            await self._emit_state(AgentState.RUNNING)
            await asyncio.sleep(self.heartbeat_interval_sec)

    async def _emit_state(self, state: AgentState) -> None:
        try:
            hb = Heartbeat(agent=self.name, state=state, metrics=dict(self._metrics))
            await self.bus.publish_model(subjects.heartbeat(self.name), hb)
        except Exception:
            logger.exception("heartbeat publish failed")

    async def on_start(self) -> None:  # noqa: B027 — optional hook by design
        """Subscriptions & warm-up — called once at start."""

    async def on_stop(self) -> None:  # noqa: B027 — optional hook by design
        """Cleanup — called once at shutdown."""
