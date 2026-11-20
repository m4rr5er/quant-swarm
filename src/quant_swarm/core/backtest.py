"""Vectorized daily-bar backtesting — pure math, no I/O.

MVP engine: one symbol, one long-only MA-cross strategy, whole-lot sizing,
next-bar-close execution (no lookahead), zero commission/slippage
(constants left for the caller to model).
"""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any

from quant_swarm.core.indicators import lot_floor


def _ma_series(values: list[float], n: int) -> list[float | None]:
    """SMA series aligned to ``values``; None until the window fills."""
    out: list[float | None] = [None] * len(values)
    acc = 0.0
    for i, v in enumerate(values):
        acc += v
        if i >= n:
            acc -= values[i - n]
        if i >= n - 1:
            out[i] = acc / n
    return out


def _stats(equity: list[float], round_trips: list[float]) -> dict[str, Any]:
    if len(equity) < 2:
        return {}
    total_ret = equity[-1] / equity[0] - 1
    peak, max_dd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak)
    rets = [b / a - 1 for a, b in pairwise(equity) if a]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
    sharpe = (mean / math.sqrt(var) * math.sqrt(252)) if var > 0 else 0.0
    wins = [r for r in round_trips if r > 0]
    return {
        "total_return": round(total_ret, 4),
        "max_drawdown": round(max_dd, 4),
        "sharpe": round(sharpe, 3),
        "n_round_trips": len(round_trips),
        "win_rate": round(len(wins) / len(round_trips), 3) if round_trips else None,
        "final_equity": round(equity[-1], 2),
    }


def backtest_ma_cross(
    closes: list[float],
    *,
    short: int = 5,
    long: int = 20,
    cash: float = 1_000_000.0,
    dates: list[str] | None = None,
) -> dict[str, Any]:
    """Golden-cross all-in / death-cross flat, filled at next bar's close.

    Returns ``{"error": ...}`` instead of raising when data is unusable —
    the caller turns that into a low-confidence card.
    """
    if short >= long:
        return {"error": f"need short < long, got {short}/{long}"}
    if len(closes) < long + 5:
        return {"error": f"need >{long + 5} bars, got {len(closes)}"}

    fast, slow = _ma_series(closes, short), _ma_series(closes, long)
    qty, entry_px = 0, 0.0
    round_trips: list[float] = []
    trades: list[dict] = []
    equity: list[float] = []
    pending: str | None = None  # signal on bar i executes at close of bar i+1

    def date_of(i: int) -> str:
        return dates[i] if dates and i < len(dates) else str(i)

    for i, px in enumerate(closes):
        if pending == "buy" and qty == 0:
            qty = lot_floor(cash / px)
            cash -= qty * px
            entry_px = px
            if qty:
                trades.append({"i": date_of(i), "side": "BUY", "px": px, "qty": qty})
        elif pending == "sell" and qty > 0:
            cash += qty * px
            round_trips.append(px / entry_px - 1)
            trades.append({"i": date_of(i), "side": "SELL", "px": px, "qty": qty})
            qty = 0
        pending = None
        equity.append(cash + qty * px)
        f, s = fast[i], slow[i]
        if f is None or s is None or i == 0 or fast[i - 1] is None or slow[i - 1] is None:
            continue
        if fast[i - 1] <= slow[i - 1] and f > s:
            pending = "buy"
        elif fast[i - 1] >= slow[i - 1] and f < s:
            pending = "sell"

    # mark the open position to market at the last close
    if qty:
        round_trips.append(closes[-1] / entry_px - 1)
    return {
        "strategy": "ma_cross",
        "params": {"short": short, "long": long},
        "stats": _stats(equity, round_trips),
        "position": qty,
        "trades": trades[-10:],
        "n_bars": len(closes),
    }


STRATEGIES = {"ma_cross": backtest_ma_cross}
