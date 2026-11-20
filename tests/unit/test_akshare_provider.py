"""AKShare provider — DataFrame -> InfoCard transform (offline stub)."""

import pandas as pd

from quant_swarm.agents.market_data.providers.akshare import AkshareMarketProvider, to_ak_code
from quant_swarm.core.schemas import CardKind


class StubProvider(AkshareMarketProvider):
    def __init__(self, df: pd.DataFrame) -> None:
        super().__init__(n_bars=40)
        self._df = df

    def _fetch(self, symbol: str) -> pd.DataFrame:
        return self._df


def _df(n: int = 40) -> pd.DataFrame:
    rows = {
        "日期": pd.date_range("2025-01-01", periods=n).strftime("%Y-%m-%d"),
        "开盘": [100.0 + i for i in range(n)],
        "最高": [102.0 + i for i in range(n)],
        "最低": [99.0 + i for i in range(n)],
        "收盘": [100.0 + i for i in range(n)],
        "成交量": [1_000_000 + i for i in range(n)],
    }
    return pd.DataFrame(rows)


def test_to_ak_code() -> None:
    assert to_ak_code("600519.SH") == "600519"
    assert to_ak_code("000001.SZ") == "000001"


async def test_card_payload() -> None:
    card = await StubProvider(_df(40)).info_card("600519.SH")
    assert card.kind is CardKind.MARKET
    assert card.agent == "market_data"
    assert card.symbols == ["600519.SH"]
    assert card.source == "akshare"

    closes = card.payload["closes"]
    assert len(closes) == 40  # n_bars tail only
    assert closes[-1] == 139.0
    assert card.payload["bars"][-1]["close"] == 139.0

    ind = card.payload["indicators"]
    assert ind["ma5"] == (135.0 + 136.0 + 137.0 + 138.0 + 139.0) / 5
    assert ind["rsi14"] is not None
    assert ind["macd"] is not None and "dif" in ind["macd"]
