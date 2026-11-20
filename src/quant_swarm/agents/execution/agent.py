"""Execution agent: order intent -> broker -> fill report + ledger.

Keeps a last-price cache per symbol from market cards (a real broker would
know quotes itself), so MARKET orders fill at the latest seen close.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from quant_swarm.agents.base import AgentBase
from quant_swarm.agents.execution.broker import Broker, PaperBroker
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, MessageBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.models import FillRow, OrderRow
from quant_swarm.core.schemas import FillStatus, InfoCard, OrderIntent


class ExecutionAgent(AgentBase):
    name = "execution"

    def __init__(
        self,
        bus: MessageBus,
        settings: Settings,
        cfg: AppConfig,
        broker: Broker | None = None,
    ) -> None:
        super().__init__(bus, settings, cfg)
        self.broker = broker or PaperBroker(
            self.sessions, initial_cash=cfg.account.initial_cash
        )
        self._last_price: dict[str, float] = {}

    async def on_start(self) -> None:
        await self.subscribe(subjects.ORDERS, self._on_order)
        await self.subscribe(subjects.CARDS_MARKET_ALL, self._on_card)
        logger.info("execution ready: broker={}", self.broker.name)

    async def _on_card(self, msg: BusMessage) -> None:
        card = msg.envelope().unwrap(InfoCard)
        closes = card.payload.get("closes") or []
        if closes:
            for symbol in card.symbols:
                self._last_price[symbol] = closes[-1]

    async def _on_order(self, msg: BusMessage) -> None:
        env = msg.envelope()
        trace = env.trace_id
        bound = logger.bind(trace_id=trace)
        order = env.unwrap(OrderIntent)
        price = order.limit_price or self._last_price.get(order.symbol)
        try:
            fill = await self.broker.place(order, price)
            await self._persist(order, fill, trace)
            await self.bus.publish_model(subjects.FILLS, fill, trace_id=trace)
            self.bump("fills" if fill.status is FillStatus.FILLED else "rejects")
            bound.info(
                "order {} {} {}x{} -> {} @{}",
                order.side,
                order.symbol,
                order.qty,
                order.order_id,
                fill.status,
                fill.avg_price,
            )
        except Exception:
            self.bump("errors")
            bound.exception("order {} failed", order.order_id)

    async def _persist(self, order: OrderIntent, fill, trace: str) -> None:
        async with self.sessions() as s:
            order_row = (
                await s.execute(select(OrderRow).where(OrderRow.order_id == order.order_id))
            ).scalar_one_or_none()
            if order_row is None:
                order_row = OrderRow(
                    order_id=order.order_id,
                    decision_id=order.decision_id,
                    ts=order.ts,
                    symbol=order.symbol,
                    side=str(order.side),
                    qty=order.qty,
                    order_type=str(order.order_type),
                    limit_price=order.limit_price,
                    tif=str(order.tif),
                    status="PENDING",
                    trace_id=trace,
                )
                s.add(order_row)
            order_row.status = str(fill.status)
            s.add(
                FillRow(
                    fill_id=fill.fill_id,
                    order_id=fill.order_id,
                    status=str(fill.status),
                    filled_qty=fill.filled_qty,
                    avg_price=fill.avg_price,
                    ts=fill.ts,
                    broker=fill.broker,
                    meta=fill.meta,
                    trace_id=trace,
                )
            )
            await s.commit()
