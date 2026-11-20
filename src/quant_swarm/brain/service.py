"""AI decision brain — the only decision outlet.

Flow: cache latest InfoCards (market + fundamental + capital) and recent
risk events -> on qs.ctrl.decide, decide per symbol via the configured LLM
profile (MACrossPolicy as offline fallback) -> guardrails (weight clamp,
veto) -> emit Decision on qs.decisions and, for trades, a sized
OrderIntent on qs.orders (target-weight semantics, 100-share lots).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from loguru import logger
from sqlalchemy import select

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, MessageBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.models import AccountRow, DecisionRow, OrderRow, PositionRow
from quant_swarm.core.indicators import lot_floor
from quant_swarm.core.llm import LLMClient, LLMConfigError
from quant_swarm.core.schemas import (
    Action,
    Decision,
    InfoCard,
    OrderIntent,
    RiskEvent,
    RiskLevel,
    Side,
)
from quant_swarm.core.timeutils import utcnow

from .llm_decider import LLMDecider
from .policy import MACrossPolicy

RISK_EVENT_WINDOW = timedelta(hours=24)


class BrainService(AgentBase):
    name = "brain"

    def __init__(
        self,
        bus: MessageBus,
        settings: Settings,
        cfg: AppConfig,
        policy: MACrossPolicy | None = None,
        decider: LLMDecider | None = None,
    ) -> None:
        super().__init__(bus, settings, cfg)
        self.policy = policy or MACrossPolicy()
        self._decider = decider if decider is not None else self._build_decider()
        self._market: dict[str, InfoCard] = {}
        self._extra: dict[str, dict[str, InfoCard]] = defaultdict(dict)
        self._risk_events: list[RiskEvent] = []

    def _build_decider(self) -> LLMDecider | None:
        profile_name = self.spec.llm_profile
        if not profile_name or not self.spec.params.get("use_llm", True):
            return None
        profile = self.cfg.llm.profiles.get(profile_name)
        if profile is None:
            logger.warning("llm profile {!r} not configured — rule policy only", profile_name)
            return None
        try:
            client = LLMClient(profile)
        except LLMConfigError as exc:
            logger.warning("{} — rule policy only", exc)
            return None
        return LLMDecider(
            client, prompt_version=str(self.spec.params.get("prompt_version", "decision_v1"))
        )

    async def on_start(self) -> None:
        await self.subscribe(subjects.CARDS_MARKET_ALL, self._on_market_card)
        await self.subscribe(subjects.CARDS_FUNDAMENTAL, self._on_extra_card)
        await self.subscribe(subjects.CARDS_CAPITAL, self._on_extra_card)
        await self.subscribe(subjects.CTRL_DECIDE, self._on_decide)
        await self.subscribe(subjects.ALERTS_EVENTS, self._on_alert)
        logger.info(
            "brain ready: decider={}",
            type(self._decider).__name__ if self._decider else "MACrossPolicy",
        )

    async def _on_market_card(self, msg: BusMessage) -> None:
        card = msg.envelope().unwrap(InfoCard)
        for symbol in card.symbols:
            self._market[symbol] = card
        self.bump("market_cards", len(card.symbols))

    async def _on_extra_card(self, msg: BusMessage) -> None:
        card = msg.envelope().unwrap(InfoCard)
        for symbol in card.symbols:
            self._extra[symbol][str(card.kind)] = card
        self.bump("extra_cards", len(card.symbols))

    async def _on_alert(self, msg: BusMessage) -> None:
        event = msg.envelope().unwrap(RiskEvent)
        self._risk_events.append(event)
        cutoff = utcnow() - RISK_EVENT_WINDOW
        self._risk_events = [e for e in self._risk_events if e.ts >= cutoff]
        self.bump("risk_events")

    def _events_for(self, symbol: str) -> list[RiskEvent]:
        return [
            e
            for e in self._risk_events
            if symbol in e.symbols or e.scope == "global"
        ]

    async def _on_decide(self, msg: BusMessage) -> None:
        trace = msg.envelope().trace_id
        bound = logger.bind(trace_id=trace)
        for symbol, card in list(self._market.items()):
            try:
                await self._decide_one(symbol, card, trace, bound)
            except Exception:
                self.bump("errors")
                bound.exception("decide failed for {}", symbol)

    async def _decide_one(self, symbol: str, card: InfoCard, trace: str, bound) -> None:
        closes = card.payload.get("closes") or []
        last_close = closes[-1] if closes else None
        position_qty = await self._position_qty(symbol)
        equity = await self._equity()
        events = self._events_for(symbol)
        max_w = self.cfg.risk.max_position_weight

        action, weight, why, llm_meta = await self._propose(
            symbol, card, closes, position_qty, equity, max_w, events, bound
        )
        action, weight, why = self._guardrails(symbol, action, weight, why, events, max_w)

        qty = self._size(action, weight, position_qty, last_close, equity)
        if action is not Action.HOLD and qty <= 0:
            action = Action.HOLD
            why = f"{why}; sized to 0 shares"
        card_refs = [card.card_id, *[c.card_id for c in self._extra[symbol].values()]]
        decision = Decision(
            symbol=symbol,
            action=action,
            target_weight=weight if action in (Action.BUY, Action.ADD) else None,
            qty=qty if action is not Action.HOLD else None,
            rationale=why,
            card_refs=card_refs,
            llm=llm_meta,
        )

        env = await self.bus.publish_model(subjects.DECISIONS, decision, trace_id=trace)
        await self._persist_decision(decision, trace)
        self.bump("decisions")
        bound.info("decision {} {} ({})", symbol, action, why)

        if action is Action.HOLD:
            return
        order = OrderIntent(
            decision_id=decision.decision_id,
            symbol=symbol,
            side=Side.BUY if action in (Action.BUY, Action.ADD) else Side.SELL,
            qty=qty,
        )
        await self.bus.publish_model(subjects.ORDERS, order, trace_id=env.trace_id)
        await self._persist_order(order, trace)
        self.bump("orders")

    async def _propose(
        self,
        symbol: str,
        card: InfoCard,
        closes: list[float],
        position_qty: int,
        equity: float,
        max_w: float,
        events: list[RiskEvent],
        bound,
    ) -> tuple[Action, float | None, str, dict | None]:
        """Ask the LLM decider first; fall back to the rule policy on error."""
        if self._decider is not None:
            try:
                out = await self._decider.decide(
                    symbol=symbol,
                    market_card=card,
                    extra_cards=list(self._extra[symbol].values()),
                    position_qty=position_qty,
                    equity=equity,
                    max_weight=max_w,
                    risk_events=events,
                )
                meta = {
                    "model": self._decider.client.profile.model,
                    "prompt_version": self._decider.prompt_version,
                    "confidence": out.confidence,
                    "usage": self._decider.client.last_usage,
                }
                return out.action, out.target_weight, out.rationale or "llm", meta
            except Exception as exc:
                bound.warning("llm decide failed for {}, policy fallback: {}", symbol, exc)
                self.bump("llm_fallback")
        action, why = self.policy.evaluate(symbol, closes, position_qty)
        weight = max_w if action in (Action.BUY, Action.ADD) else None
        return action, weight, f"policy: {why}", None

    def _guardrails(
        self,
        symbol: str,
        action: Action,
        weight: float | None,
        why: str,
        events: list[RiskEvent],
        max_w: float,
    ) -> tuple[Action, float | None, str]:
        """Hard limits the model cannot override."""
        veto = next(
            (e for e in reversed(events) if e.level is RiskLevel.CRITICAL and e.veto),
            None,
        )
        if veto is not None and action in (Action.BUY, Action.ADD):
            return Action.HOLD, None, f"{why}; vetoed by {veto.code}"
        if weight is not None and weight > max_w:
            why = f"{why}; weight {weight:.2f} clamped to {max_w:.2f}"
            weight = max_w
        if action in (Action.BUY, Action.ADD) and weight is None:
            weight = max_w
        return action, weight, why

    def _size(
        self,
        action: Action,
        weight: float | None,
        position_qty: int,
        last_close: float | None,
        equity: float,
    ) -> int:
        """Target-weight sizing: qty needed to move the position to ``weight``."""
        if last_close is None or last_close <= 0:
            return position_qty if action in (Action.SELL, Action.REDUCE) else 0
        desired = lot_floor(equity * (weight or 0.0) / last_close)
        if action in (Action.BUY, Action.ADD):
            return max(0, desired - position_qty)
        if action in (Action.SELL, Action.REDUCE):
            return position_qty if weight is None else max(0, position_qty - desired)
        return 0

    async def _position_qty(self, symbol: str) -> int:
        async with self.sessions() as s:
            row = (
                await s.execute(select(PositionRow).where(PositionRow.symbol == symbol))
            ).scalar_one_or_none()
            return row.qty if row else 0

    async def _equity(self) -> float:
        async with self.sessions() as s:
            row = (
                await s.execute(select(AccountRow).where(AccountRow.account_id == "paper"))
            ).scalar_one_or_none()
            return row.equity if row else self.cfg.account.initial_cash

    async def _persist_decision(self, d: Decision, trace: str) -> None:
        async with self.sessions() as s:
            s.add(
                DecisionRow(
                    decision_id=d.decision_id,
                    ts=d.ts,
                    symbol=d.symbol,
                    action=str(d.action),
                    target_weight=d.target_weight,
                    qty=d.qty,
                    horizon=d.horizon,
                    rationale=d.rationale,
                    card_refs=d.card_refs,
                    llm=d.llm,
                    trace_id=trace,
                )
            )
            await s.commit()

    async def _persist_order(self, o: OrderIntent, trace: str) -> None:
        async with self.sessions() as s:
            s.add(
                OrderRow(
                    order_id=o.order_id,
                    decision_id=o.decision_id,
                    ts=utcnow(),
                    symbol=o.symbol,
                    side=str(o.side),
                    qty=o.qty,
                    order_type=str(o.order_type),
                    limit_price=o.limit_price,
                    tif=str(o.tif),
                    status="PENDING",
                    trace_id=trace,
                )
            )
            await s.commit()
