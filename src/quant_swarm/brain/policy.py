"""Rule policy — MA crossover. The LLM decision path augments this in M2.

Kept deliberately small: it maps a close series + current position to an
Action plus a human-readable rationale. The LLM client is wired separately
via ``brain/service.py`` so the rule engine remains the offline fallback.
"""

from __future__ import annotations

from quant_swarm.core.indicators import sma
from quant_swarm.core.schemas import Action


class MACrossPolicy:
    """Golden/death cross on short vs long SMA."""

    def __init__(self, short: int = 5, long: int = 20) -> None:
        self.short = short
        self.long = long

    def evaluate(
        self, symbol: str, closes: list[float], position_qty: int
    ) -> tuple[Action, str]:
        prev_s = sma(closes[:-1], self.short)
        prev_l = sma(closes[:-1], self.long)
        cur_s = sma(closes, self.short)
        cur_l = sma(closes, self.long)
        if None in (prev_s, prev_l, cur_s, cur_l):
            return Action.HOLD, f"insufficient data ({len(closes)} closes)"

        if prev_s <= prev_l and cur_s > cur_l:  # type: ignore[operator]
            act = Action.ADD if position_qty > 0 else Action.BUY
            return act, f"golden cross ma{self.short} {cur_s:.2f} > ma{self.long} {cur_l:.2f}"
        if prev_s >= prev_l and cur_s < cur_l:  # type: ignore[operator]
            act = Action.REDUCE if position_qty > 0 else Action.HOLD
            if act is Action.REDUCE:
                return act, f"death cross ma{self.short} {cur_s:.2f} < ma{self.long} {cur_l:.2f}"
            return act, f"death cross but flat ({cur_s:.2f} < {cur_l:.2f})"
        return Action.HOLD, f"no cross (ma{self.short} {cur_s:.2f}, ma{self.long} {cur_l:.2f})"
