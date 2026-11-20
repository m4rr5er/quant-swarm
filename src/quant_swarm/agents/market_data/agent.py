"""Market-data agent: on collect, emits one InfoCard per watched symbol."""

from __future__ import annotations

from loguru import logger

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, MessageBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.models import InfoCardRow
from quant_swarm.core.schemas import InfoCard
from quant_swarm.core.timeutils import utcnow

from .providers import MarketDataProvider, make_provider


class MarketDataAgent(AgentBase):
    name = "market_data"

    def __init__(
        self,
        bus: MessageBus,
        settings: Settings,
        cfg: AppConfig,
        provider: MarketDataProvider | None = None,
    ) -> None:
        super().__init__(bus, settings, cfg)
        self.provider = provider or make_provider(self.spec)

    async def on_start(self) -> None:
        await self.subscribe(subjects.ctrl_collect(self.name), self._on_collect)
        logger.info(
            "market_data ready: provider={}, watchlist={}",
            self.provider.name,
            self.cfg.watchlist,
        )

    async def _on_collect(self, msg: BusMessage) -> None:
        trace = msg.envelope().trace_id
        bound = logger.bind(trace_id=trace)
        for symbol in self.cfg.watchlist:
            try:
                card = await self.provider.info_card(symbol)
                await self.bus.publish_model(
                    subjects.cards_market(symbol), card, trace_id=trace
                )
                await self._persist(card, trace)
                self.bump("cards")
            except Exception:
                self.bump("errors")
                bound.exception("collect failed for {}", symbol)
        bound.info("collect done: {} symbols", len(self.cfg.watchlist))

    async def _persist(self, card: InfoCard, trace: str) -> None:
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
