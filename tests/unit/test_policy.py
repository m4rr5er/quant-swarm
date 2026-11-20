"""MACrossPolicy — golden/death cross logic."""

from quant_swarm.brain.policy import MACrossPolicy
from quant_swarm.core.schemas import Action

POLICY = MACrossPolicy(short=5, long=20)


def test_golden_cross_buys_when_flat() -> None:
    closes = [100.0] * 24 + [130.0]
    action, why = POLICY.evaluate("X", closes, position_qty=0)
    assert action is Action.BUY
    assert "golden cross" in why


def test_golden_cross_adds_when_holding() -> None:
    closes = [100.0] * 24 + [130.0]
    action, _ = POLICY.evaluate("X", closes, position_qty=100)
    assert action is Action.ADD


def test_death_cross_reduces_when_holding() -> None:
    closes = [100.0] * 24 + [60.0]
    action, why = POLICY.evaluate("X", closes, position_qty=100)
    assert action is Action.REDUCE
    assert "death cross" in why


def test_death_cross_holds_when_flat() -> None:
    closes = [100.0] * 24 + [60.0]
    action, _ = POLICY.evaluate("X", closes, position_qty=0)
    assert action is Action.HOLD


def test_no_cross_holds() -> None:
    action, _ = POLICY.evaluate("X", [100.0] * 30, position_qty=0)
    assert action is Action.HOLD


def test_insufficient_data_holds() -> None:
    action, why = POLICY.evaluate("X", [100.0] * 10, position_qty=0)
    assert action is Action.HOLD
    assert "insufficient" in why
