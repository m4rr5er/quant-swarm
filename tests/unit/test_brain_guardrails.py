"""Brain guardrails + target-weight sizing (pure service methods)."""

import pytest

from quant_swarm.brain.service import BrainService
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AppConfig, RiskSettings, Settings
from quant_swarm.core.schemas import Action, RiskEvent, RiskLevel


@pytest.fixture
def brain(tmp_path) -> BrainService:
    cfg = AppConfig(risk=RiskSettings(max_position_weight=0.2))
    return BrainService(
        LocalBus(), Settings(bus="local", db_path=str(tmp_path / "b.db")), cfg
    )


def _veto() -> RiskEvent:
    return RiskEvent(
        code="PRICE_SPIKE_DOWN", level=RiskLevel.CRITICAL, symbols=["X"], veto=True
    )


def test_weight_clamped_to_cap(brain: BrainService) -> None:
    action, weight, why = brain._guardrails("X", Action.BUY, 0.6, "r", [], 0.2)
    assert action is Action.BUY
    assert weight == pytest.approx(0.2)
    assert "clamped" in why


def test_buy_gets_default_weight(brain: BrainService) -> None:
    _, weight, _ = brain._guardrails("X", Action.BUY, None, "r", [], 0.2)
    assert weight == pytest.approx(0.2)


def test_critical_veto_blocks_buy(brain: BrainService) -> None:
    action, weight, why = brain._guardrails("X", Action.BUY, 0.1, "r", [_veto()], 0.2)
    assert action is Action.HOLD and weight is None
    assert "vetoed" in why


def test_veto_does_not_block_sell(brain: BrainService) -> None:
    action, _, _ = brain._guardrails("X", Action.SELL, None, "r", [_veto()], 0.2)
    assert action is Action.SELL


def test_size_buys_up_to_target(brain: BrainService) -> None:
    # equity 100k, weight 30%, price 50 -> desired 600; already hold 200 -> +400
    assert brain._size(Action.ADD, 0.3, 200, 50.0, 100_000.0) == 400
    # already at/above target -> nothing to add
    assert brain._size(Action.ADD, 0.3, 800, 50.0, 100_000.0) == 0


def test_size_sells_down_to_target(brain: BrainService) -> None:
    # hold 600; keep 0.2*100k/50 = 400 -> sell 200
    assert brain._size(Action.REDUCE, 0.2, 600, 50.0, 100_000.0) == 200
    # no weight -> full exit
    assert brain._size(Action.SELL, None, 600, 50.0, 100_000.0) == 600
