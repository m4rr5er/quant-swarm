"""Market-data provider factory — mock for M1, akshare/tushare land in M2."""

from __future__ import annotations

from quant_swarm.core.config import AgentSpec

from .base import MarketDataProvider
from .mock import MockMarketProvider


def make_provider(spec: AgentSpec) -> MarketDataProvider:
    name = spec.provider or "mock"
    if name == "mock":
        return MockMarketProvider(
            seed=int(spec.params.get("seed", 42)),
            n_bars=int(spec.params.get("n_bars", 60)),
        )
    if name == "akshare":
        from .akshare import AkshareMarketProvider

        return AkshareMarketProvider(
            n_bars=int(spec.params.get("n_bars", 60)),
            adjust=str(spec.params.get("adjust", "qfq")),
        )
    if name == "tushare":
        raise NotImplementedError("provider 'tushare' needs a token — later milestone")
    raise ValueError(f"unknown market-data provider: {name!r}")


__all__ = ["MarketDataProvider", "MockMarketProvider", "make_provider"]
