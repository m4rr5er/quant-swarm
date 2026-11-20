"""Backtester agent — the quant expert's evidence engine.

On ``qs.ctrl.backtest`` ({symbol, strategy, params, n_bars}) it fetches
daily bars via the configured provider, runs a vectorized replay
(core.backtest) and emits a BACKTEST InfoCard on ``qs.cards.backtest``
with performance stats + recent trades.
"""

from __future__ import annotations

from loguru import logger

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.backtest import STRATEGIES
from quant_swarm.core.bus.base import BusMessage, MessageBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.schemas import CardKind, CtrlCommand, InfoCard
from quant_swarm.core.timeutils import utcnow


def _make_provider(spec) -> object:
    """Reuse market_data providers — same data, different consumer."""
    from quant_swarm.agents.market_data.providers.akshare import AkshareMarketProvider
    from quant_swarm.agents.market_data.providers.mock import MockMarketProvider

    name = spec.provider or "mock"
    n = int(spec.params.get("n_bars", 250))
    if name == "akshare":
        return AkshareMarketProvider(n_bars=n, adjust=spec.params.get("adjust", "qfq"))
    return MockMarketProvider(n_bars=n, seed=spec.params.get("seed"))


class BacktesterAgent(AgentBase):
    name = "backtester"

    def __init__(self, bus: MessageBus, settings: Settings, cfg: AppConfig) -> None:
        super().__init__(bus, settings, cfg)
        self.provider = _make_provider(self.spec)

    async def on_start(self) -> None:
        await self.subscribe(subjects.CTRL_BACKTEST, self._on_backtest)
        logger.info("backtester ready (provider={})", self.provider.name)

    async def _on_backtest(self, msg: BusMessage) -> None:
        trace = msg.envelope().trace_id
        cmd = msg.envelope().unwrap(CtrlCommand)
        args = cmd.args
        symbol = str(args.get("symbol", "")).upper()
        strategy = args.get("strategy", "ma_cross")
        fn = STRATEGIES.get(strategy)
        if not symbol or fn is None:
            logger.warning("bad backtest args: {}", args)
            return

        try:
            card = await self.provider.info_card(symbol)
            closes = card.payload["closes"]
            bars = card.payload.get("bars", [])
        except Exception as exc:
            logger.warning("backtest data fetch failed for {}: {}", symbol, exc)
            card, closes, bars = None, [], []

        params = dict(args.get("params", {}))
        result = fn(closes, dates=[b.get("date") for b in bars], **params) if closes else {}
        if not closes:
            result = {"error": f"no bars for {symbol}"}

        out = InfoCard(
            agent=self.name,
            kind=CardKind.BACKTEST,
            symbols=[symbol],
            asof=utcnow(),
            ttl_sec=int(self.spec.params.get("ttl_sec", 86400)),
            confidence=0.9 if "error" not in result else 0.2,
            source=str(self.provider.name),
            payload={
                "strategy": strategy,
                "params": params,
                "n_bars": len(closes),
                **result,
            },
        )
        await self.bus.publish_model(subjects.CARDS_BACKTEST, out, trace_id=trace)
        await self.persist_card(out, trace)
        self.bump("backtests")
        logger.info(
            "backtest {} {} -> {}",
            symbol,
            strategy,
            result.get("stats", result.get("error")),
        )
