"""Capital-flow agent (Agent 3) — main-fund net inflow per symbol via akshare."""

from __future__ import annotations

import asyncio

from quant_swarm.agents.base import AgentBase
from quant_swarm.agents.market_data.providers.akshare import to_ak_code
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, MessageBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.schemas import CardKind, InfoCard
from quant_swarm.core.timeutils import utcnow


def _market_of(symbol: str) -> str:
    return "sh" if symbol.upper().endswith(".SH") else "sz"


class CapitalFlowAgent(AgentBase):
    name = "capital_flow"
    ctrl_subject = subjects.ctrl_collect("capital_flow")

    def __init__(self, bus: MessageBus, settings: Settings, cfg: AppConfig) -> None:
        super().__init__(bus, settings, cfg)
        self._days = int(self.spec.params.get("days", 5))

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
                self.bound.warning("fund flow failed for {}: {}", symbol, exc)
                continue
            await self.bus.publish_model(subjects.CARDS_CAPITAL, card, trace_id=trace)
            await self.persist_card(card, trace)
            self.bump("cards")
        self.bound.info("collect done: {} symbols", len(self.cfg.watchlist))

    async def _card(self, symbol: str) -> InfoCard:
        rows = await asyncio.to_thread(self._flow, symbol)
        return InfoCard(
            agent=self.name,
            kind=CardKind.CAPITAL,
            symbols=[symbol],
            asof=utcnow(),
            ttl_sec=43200,
            source="akshare",
            payload={"fund_flow": rows},
        )

    def _flow(self, symbol: str) -> list[dict]:
        import akshare as ak

        df = ak.stock_fund_flow_individual_hist_em(
            symbol=to_ak_code(symbol), market=_market_of(symbol)
        )
        if df is None or df.empty:
            return []
        tail = df.tail(self._days)
        return [
            {str(k): _clean(v) for k, v in row.items()}
            for row in tail.to_dict(orient="records")
        ]


def _clean(v):
    """JSON-safe cell: keep numerics, stringify the rest (dates etc.)."""
    if str(v) in ("nan", "NaT", "None"):
        return None
    return v if isinstance(v, (int, float)) else str(v)
