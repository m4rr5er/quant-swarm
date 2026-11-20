"""AKShare provider — real A-share daily bars (eastmoney backend, no token)."""

from __future__ import annotations

import asyncio

from quant_swarm.core.indicators import macd, rsi, sma
from quant_swarm.core.schemas import CardKind, InfoCard
from quant_swarm.core.timeutils import utcnow

from .base import MarketDataProvider


def to_ak_code(symbol: str) -> str:
    """``600519.SH`` -> ``600519`` (akshare uses bare 6-digit codes)."""
    return symbol.split(".")[0]


class AkshareMarketProvider(MarketDataProvider):
    name = "akshare"

    def __init__(self, *, n_bars: int = 60, adjust: str = "qfq") -> None:
        self._n = n_bars
        self._adjust = adjust

    async def info_card(self, symbol: str) -> InfoCard:
        df = await asyncio.to_thread(self._fetch, symbol)
        closes = df["收盘"].astype(float).tolist()[-self._n :]
        bars = [
            {
                "date": str(r["日期"]),
                "open": float(r["开盘"]),
                "high": float(r["最高"]),
                "low": float(r["最低"]),
                "close": float(r["收盘"]),
                "volume": float(r["成交量"]),
            }
            for _, r in df.tail(self._n).iterrows()
        ]
        payload = {
            "interval": "1d",
            "adjust": self._adjust,
            "closes": closes,
            "bars": bars,
            "indicators": {
                "ma5": sma(closes, 5),
                "ma20": sma(closes, 20),
                "rsi14": rsi(closes, 14),
                "macd": macd(closes),
            },
        }
        return InfoCard(
            agent="market_data",
            kind=CardKind.MARKET,
            symbols=[symbol],
            asof=utcnow(),
            source="akshare",
            payload=payload,
        )

    def _fetch(self, symbol: str):
        import akshare as ak

        df = ak.stock_zh_a_hist_em(
            symbol=to_ak_code(symbol), period="daily", adjust=self._adjust
        )
        if df is None or df.empty:
            raise RuntimeError(f"akshare returned no data for {symbol}")
        return df
