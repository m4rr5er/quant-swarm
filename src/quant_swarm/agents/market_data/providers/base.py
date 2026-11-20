"""MarketDataProvider — pluggable data source contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from quant_swarm.core.schemas import InfoCard


class MarketDataProvider(ABC):
    name: str = "provider"

    @abstractmethod
    async def info_card(self, symbol: str) -> InfoCard:
        """Collect data for ``symbol`` and return a standardized MARKET card."""
