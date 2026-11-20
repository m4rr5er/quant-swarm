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
from quant_swarm.core.bus.base import Handler, MessageBus, Subscription
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
        self, subject: str, handler: Handler, *, queue_group: str | None = None
    ) -> Subscription:
        sub = await self.bus.subscribe(subject, handler, queue_group=queue_group)
        self._subs.append(sub)
        return sub

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
