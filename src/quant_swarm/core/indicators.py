"""Technical indicators — shared math usable by any agent or the brain.

Pure functions, no I/O. Keep them dependency-free (no pandas/ta-lib) so the
contracts stay light; swap for a proper TA lib later if needed.
"""

from __future__ import annotations

from itertools import pairwise


def sma(values: list[float], n: int) -> float | None:
    """Simple moving average over the last ``n`` values; None if insufficient."""
    if n <= 0 or len(values) < n:
        return None
    return sum(values[-n:]) / n


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder-smoothed RSI; None if insufficient data."""
    if len(closes) < period + 1:
        return None
    deltas = [b - a for a, b in pairwise(closes)]
    gains = [max(d, 0.0) for d in deltas[-period:]]
    losses = [max(-d, 0.0) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def lot_floor(qty: float, lot: int = 100) -> int:
    """Round down to whole lots (A-share 100-share minimum)."""
    return int(qty // lot) * lot


def ema_series(values: list[float], n: int) -> list[float]:
    """Full EMA series (seeded with the first value); empty if input empty."""
    if not values:
        return []
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> dict[str, float] | None:
    """MACD dif/dea/hist for the latest bar; None if insufficient data."""
    if len(closes) < slow + signal:
        return None
    dif = [f - s for f, s in zip(ema_series(closes, fast), ema_series(closes, slow), strict=True)]
    dea = ema_series(dif, signal)
    return {
        "dif": dif[-1],
        "dea": dea[-1],
        "hist": (dif[-1] - dea[-1]) * 2,
    }
