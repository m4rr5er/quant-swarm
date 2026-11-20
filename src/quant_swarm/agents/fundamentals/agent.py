"""Fundamentals agent (Agent 2) — basic company snapshot via akshare.

Minimal M2 version: per-symbol profile + valuation snapshot as a
FUNDAMENTAL InfoCard. News NLP sentiment comes later.
"""

from __future__ import annotations

import asyncio

from quant_swarm.agents.base import AgentBase
from quant_swarm.agents.market_data.providers.akshare import to_ak_code
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, MessageBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.schemas import CardKind, InfoCard
from quant_swarm.core.timeutils import utcnow


class FundamentalsAgent(AgentBase):
    name = "fundamentals"
    ctrl_subject = subjects.ctrl_collect("fundamentals")

    def __init__(self, bus: MessageBus, settings: Settings, cfg: AppConfig) -> None:
        super().__init__(bus, settings, cfg)
        self._collect_count = 0

    async def on_start(self) -> None:
        await self.subscribe(self.ctrl_subject, self._on_collect)
        self.bound.info("subscribed {}", self.ctrl_subject)

    async def _on_collect(self, msg: BusMessage) -> None:
        trace = msg.envelope().trace_id
        for symbol in self.cfg.watchlist:
            try:
                card = await self._card(symbol)
            except Exception as exc:
                self.bump("errors")
                self.bound.warning("snapshot failed for {}: {}", symbol, exc)
                continue
            await self.bus.publish_model(subjects.CARDS_FUNDAMENTAL, card, trace_id=trace)
            await self.persist_card(card, trace)
            self.bump("cards")
        self._collect_count += 1
        self.bound.info("collect done: {} symbols", len(self.cfg.watchlist))

    async def _card(self, symbol: str) -> InfoCard:
        items = await asyncio.to_thread(self._snapshot, symbol)
        return InfoCard(
            agent=self.name,
            kind=CardKind.FUNDAMENTAL,
            symbols=[symbol],
            asof=utcnow(),
            ttl_sec=86400,
            source="akshare",
            payload={"snapshot": items},
        )

    @staticmethod
    def _snapshot(symbol: str) -> dict[str, str]:
        import akshare as ak

        df = ak.stock_individual_info_em(symbol=to_ak_code(symbol))
        return {str(r["item"]): str(r["value"]) for _, r in df.iterrows()}

    def metrics(self) -> dict[str, int | float | str]:
        return {**self._metrics, "collect_count": self._collect_count}
