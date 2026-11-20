"""Deterministic mock provider — seeded random walk, fully reproducible.

``closes`` overrides let tests inject an exact close series (e.g. to force
an MA crossover); otherwise a per-symbol seeded walk is generated.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from quant_swarm.core.indicators import rsi, sma
from quant_swarm.core.schemas import CardKind, InfoCard
from quant_swarm.core.timeutils import utcnow

from .base import MarketDataProvider


class MockMarketProvider(MarketDataProvider):
    name = "mock"

    def __init__(
        self,
        *,
        seed: int = 42,
        n_bars: int = 60,
        closes: dict[str, list[float]] | None = None,
    ) -> None:
        self._seed = seed
        self._n_bars = n_bars
        self._overrides = closes or {}

    async def info_card(self, symbol: str) -> InfoCard:
        closes = self._overrides.get(symbol) or self._walk(symbol)
        payload = {
            "interval": "1d",
            "closes": closes,
            "bars": self._bars(closes),
            "indicators": {
                "ma5": sma(closes, 5),
                "ma20": sma(closes, 20),
                "rsi14": rsi(closes, 14),
            },
        }
        return InfoCard(
            agent="market_data",
            kind=CardKind.MARKET,
            symbols=[symbol],
            asof=utcnow(),
            source="mock",
            payload=payload,
        )

    def _walk(self, symbol: str) -> list[float]:
        rng = random.Random(f"{self._seed}:{symbol}")
        price = 10.0 + rng.random() * 90.0
        return [round(price := price * (1 + rng.gauss(0.0, 0.015)), 2) for _ in range(self._n_bars)]

    @staticmethod
    def _bars(closes: list[float]) -> list[dict]:
        today = date.today()
        first = today - timedelta(days=len(closes) - 1)
        return [
            {
                "date": (first + timedelta(days=i)).isoformat(),
                "open": c,
                "high": c,
                "low": c,
                "close": c,
                "volume": 1_000_000,
            }
            for i, c in enumerate(closes)
        ]
