"""AI decision brain — the only decision outlet.

M1 flow: collect market InfoCards -> on qs.ctrl.decide evaluate the rule
policy per symbol -> emit Decision on qs.decisions and, for trades, a sized
OrderIntent on qs.orders (100-share lots against paper equity).

M2 will call the configured LLM profile here; the policy stays the fallback.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, MessageBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.models import AccountRow, DecisionRow, OrderRow, PositionRow
from quant_swarm.core.indicators import lot_floor
from quant_swarm.core.schemas import Action, Decision, InfoCard, OrderIntent, Side
from quant_swarm.core.timeutils import utcnow

from .policy import MACrossPolicy


class BrainService(AgentBase):
    name = "brain"

    def __init__(
        self,
        bus: MessageBus,
        settings: Settings,
        cfg: AppConfig,
        policy: MACrossPolicy | None = None,
    ) -> None:
        super().__init__(bus, settings, cfg)
        self.policy = policy or MACrossPolicy()
        self._latest: dict[str, tuple[InfoCard, str]] = {}  # symbol -> (card, trace)

    async def on_start(self) -> None:
        await self.subscribe(subjects.CARDS_MARKET_ALL, self._on_card)
        await self.subscribe(subjects.CTRL_DECIDE, self._on_decide)
        await self.subscribe(subjects.ALERTS_EVENTS, self._on_alert)
        logger.info("brain ready: policy={}", type(self.policy).__name__)

    async def _on_card(self, msg: BusMessage) -> None:
        env = msg.envelope()
        card = env.unwrap(InfoCard)
        for symbol in card.symbols:
            self._latest[symbol] = (card, env.trace_id)
        self.bump("cards_seen", len(card.symbols))

    async def _on_alert(self, msg: BusMessage) -> None:
        # Risk-event handling lands with the risk agent in M4; log for now.
        logger.bind(trace_id=msg.envelope().trace_id).warning("risk event seen")

    async def _on_decide(self, msg: BusMessage) -> None:
        trace = msg.envelope().trace_id
        bound = logger.bind(trace_id=trace)
        for symbol, (card, _card_trace) in list(self._latest.items()):
            try:
                await self._decide_one(symbol, card, trace, bound)
            except Exception:
                self.bump("errors")
                bound.exception("decide failed for {}", symbol)

    async def _decide_one(self, symbol: str, card: InfoCard, trace: str, bound) -> None:
        closes = card.payload.get("closes") or []
        last_close = closes[-1] if closes else None
        position_qty = await self._position_qty(symbol)
        action, why = self.policy.evaluate(symbol, closes, position_qty)

        qty = await self._size(symbol, action, position_qty, last_close)
        if action is not Action.HOLD and qty <= 0:
            action = Action.HOLD
            why = f"{why}; sized to 0 shares"
        decision = Decision(
            symbol=symbol,
            action=action,
            target_weight=(
                self.cfg.risk.max_position_weight
                if action in (Action.BUY, Action.ADD)
                else None
            ),
            qty=qty if action is not Action.HOLD else None,
            rationale=why,
            card_refs=[card.card_id],
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

    async def _size(
        self, symbol: str, action: Action, position_qty: int, last_close: float | None
    ) -> int:
        if action in (Action.SELL, Action.REDUCE):
            return position_qty
        if last_close is None or last_close <= 0:
            return 0
        equity = await self._equity()
        budget = equity * self.cfg.risk.max_position_weight
        return lot_floor(budget / last_close)

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
