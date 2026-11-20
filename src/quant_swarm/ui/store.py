"""DashboardStore — the UI's data layer (no Qt, headless-testable).

Subscribes to the bus like any other component (observer, never a
commander) and keeps the latest state in memory; heavier history comes
from sqlite on demand. ``on_change`` listeners are invoked after every
mutation — the window registers its refresh there.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, MessageBus, Subscription
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.engine import session_factory
from quant_swarm.core.db.models import (
    AccountRow,
    DecisionRow,
    InfoCardRow,
    MessageRow,
    PositionRow,
)
from quant_swarm.core.ids import new_id
from quant_swarm.core.schemas import (
    ChatMessage,
    ChatRole,
    Decision,
    FillReport,
    Heartbeat,
    InfoCard,
    RiskEvent,
)

CARD_SUBJECTS = (
    subjects.CARDS_MARKET_ALL,
    subjects.CARDS_FUNDAMENTAL,
    subjects.CARDS_CAPITAL,
)


class DashboardStore:
    def __init__(
        self, bus: MessageBus, settings: Settings, cfg: AppConfig, *, maxlen: int = 200
    ) -> None:
        self.bus = bus
        self.settings = settings
        self.cfg = cfg
        self.sessions = session_factory(settings.db_path)

        self.heartbeats: dict[str, Heartbeat] = {}
        self.cards: deque[InfoCard] = deque(maxlen=maxlen)
        self.decisions: deque[Decision] = deque(maxlen=maxlen)
        self.fills: deque[FillReport] = deque(maxlen=maxlen)
        self.risk_events: deque[RiskEvent] = deque(maxlen=maxlen)
        self.chat: deque[ChatMessage] = deque(maxlen=maxlen)
        self.chat_session_id = new_id("sess")
        self._card_by_id: dict[str, InfoCard] = {}

        self._listeners: list[Callable[[], None]] = []
        self._subs: list[Subscription] = []

    # -- listeners -------------------------------------------------------
    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in self._listeners:
            cb()

    # -- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        for subject, handler in (
            (subjects.HEARTBEAT_ALL, self._on_heartbeat),
            (subjects.DECISIONS, self._on_decision),
            (subjects.FILLS, self._on_fill),
            (subjects.ALERTS_EVENTS, self._on_risk),
            (subjects.CHAT_OUT_ALL, self._on_chat),
            *[(s, self._on_card) for s in CARD_SUBJECTS],
        ):
            self._subs.append(await self.bus.subscribe(subject, handler))
        await self._warm_card_cache()
        await self._warm_chat_history()

    async def stop(self) -> None:
        for sub in self._subs:
            await sub.unsubscribe()
        self._subs.clear()

    # -- bus handlers ----------------------------------------------------
    async def _on_heartbeat(self, msg: BusMessage) -> None:
        hb = msg.envelope().unwrap(Heartbeat)
        self.heartbeats[hb.agent] = hb
        self._notify()

    async def _on_card(self, msg: BusMessage) -> None:
        card = msg.envelope().unwrap(InfoCard)
        self.cards.appendleft(card)
        self._card_by_id[card.card_id] = card
        self._notify()

    async def _on_decision(self, msg: BusMessage) -> None:
        self.decisions.appendleft(msg.envelope().unwrap(Decision))
        self._notify()

    async def _on_fill(self, msg: BusMessage) -> None:
        self.fills.appendleft(msg.envelope().unwrap(FillReport))
        self._notify()

    async def _on_risk(self, msg: BusMessage) -> None:
        self.risk_events.appendleft(msg.envelope().unwrap(RiskEvent))
        self._notify()

    async def _on_chat(self, msg: BusMessage) -> None:
        self.chat.append(msg.envelope().unwrap(ChatMessage))
        self._notify()

    # -- chat -------------------------------------------------------------
    async def send_chat(self, text: str) -> None:
        """Publish a user ChatMessage on qs.chat.in and echo it locally."""
        msg = ChatMessage(
            session_id=self.chat_session_id,
            role=ChatRole.USER,
            content=text,
        )
        self.chat.append(msg)
        self._notify()
        await self.bus.publish_model(subjects.CHAT_IN, msg)

    async def _warm_chat_history(self, limit: int = 50) -> None:
        """Load recent dashboard-channel messages for continuity."""
        async with self.sessions() as s:
            rows = (
                (
                    await s.execute(
                        select(MessageRow)
                        .where(MessageRow.channel == "dashboard")
                        .order_by(MessageRow.ts.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        for r in reversed(rows):
            self.chat.append(
                ChatMessage(
                    session_id=r.session_id,
                    role=ChatRole(r.role),
                    expert=r.expert,
                    content=r.content,
                    refs=r.refs or [],
                    ts=r.ts,
                )
            )
        if rows:
            self._notify()

    # -- db reads --------------------------------------------------------
    async def _warm_card_cache(self, limit: int = 100) -> None:
        """Preload recent cards so decision card_refs resolve at open."""
        async with self.sessions() as s:
            rows = (
                (
                    await s.execute(
                        select(InfoCardRow).order_by(InfoCardRow.received_ts.desc()).limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        for r in rows:
            self._card_by_id.setdefault(
                r.card_id,
                InfoCard(
                    card_id=r.card_id,
                    agent=r.agent,
                    kind=r.kind,
                    symbols=r.symbols or [],
                    asof=r.asof,
                    ttl_sec=r.ttl_sec,
                    confidence=r.confidence,
                    source=r.source,
                    payload=r.payload or {},
                ),
            )

    async def positions(self) -> list[PositionRow]:
        async with self.sessions() as s:
            return list((await s.execute(select(PositionRow))).scalars().all())

    async def account(self) -> AccountRow | None:
        async with self.sessions() as s:
            return (
                await s.execute(select(AccountRow).where(AccountRow.account_id == "paper"))
            ).scalar_one_or_none()

    async def decision_history(self, limit: int = 100) -> list[DecisionRow]:
        async with self.sessions() as s:
            return list(
                (
                    await s.execute(
                        select(DecisionRow).order_by(DecisionRow.ts.desc()).limit(limit)
                    )
                )
                .scalars()
                .all()
            )

    async def card_detail(self, card_id: str) -> dict[str, Any] | None:
        """Resolve a card_id to its full payload (memory first, then db)."""
        card = self._card_by_id.get(card_id)
        if card is not None:
            return card.model_dump(mode="json")
        async with self.sessions() as s:
            row = (
                await s.execute(select(InfoCardRow).where(InfoCardRow.card_id == card_id))
            ).scalar_one_or_none()
        return (
            {
                "card_id": row.card_id,
                "agent": row.agent,
                "kind": row.kind,
                "symbols": row.symbols,
                "asof": row.asof.isoformat(),
                "source": row.source,
                "payload": row.payload,
            }
            if row
            else None
        )
