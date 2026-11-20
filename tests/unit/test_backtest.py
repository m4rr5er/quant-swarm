"""MA-cross backtest engine — signals, sizing, stats."""

from quant_swarm.core.backtest import backtest_ma_cross


def _wave(down: int, up: int, tail: int) -> list[float]:
    """Down-then-up-then-down: forces a golden cross mid-series, death after."""
    prices, p = [], 100.0
    for i in range(down + up + tail):
        if i < down:
            p -= 3.0
        elif i < down + up:
            p += 3.0
        else:
            p -= 3.0
        prices.append(round(p, 2))
    return prices


def test_golden_then_death_cross_round_trip() -> None:
    closes = _wave(15, 15, 10)
    r = backtest_ma_cross(closes, short=3, long=8)
    assert "error" not in r
    assert r["n_bars"] == 40
    sides = [t["side"] for t in r["trades"]]
    assert sides[0] == "BUY"
    if len(sides) > 1:
        assert sides[1] == "SELL"
    s = r["stats"]
    assert s["n_round_trips"] >= 1
    assert 0.0 <= s["max_drawdown"] <= 1.0
    assert "total_return" in s and "sharpe" in s and "final_equity" in s


def test_uptrend_only_buys_and_holds() -> None:
    # flat start so the cross event exists, then a steady rise
    closes = [10.0] * 15 + [10.0 + i for i in range(25)]
    r = backtest_ma_cross(closes, short=3, long=8)
    assert r["position"] > 0  # still holding at the end
    assert r["stats"]["total_return"] > 0


def test_bad_params_and_short_data() -> None:
    assert "error" in backtest_ma_cross([1.0] * 50, short=20, long=5)
    assert "error" in backtest_ma_cross([1.0] * 10, short=5, long=20)


def test_whole_lots_only() -> None:
    closes = _wave(15, 15, 10)
    r = backtest_ma_cross(closes, short=3, long=8, cash=50_000)
    for t in r["trades"]:
        if t["side"] == "BUY":
            assert t["qty"] % 100 == 0
