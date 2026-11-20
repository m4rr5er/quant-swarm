"""Contract tests — schema round-trips through the wire format."""

import pytest
from pydantic import BaseModel, ValidationError

from quant_swarm.core.schemas import (
    Action,
    CardKind,
    Decision,
    Envelope,
    FillReport,
    FillStatus,
    Heartbeat,
    InfoCard,
    OrderIntent,
    OrderType,
    RiskEvent,
    RiskLevel,
    Side,
)
from quant_swarm.core.timeutils import utcnow


def _roundtrip(model: BaseModel) -> Envelope:
    env = Envelope.wrap(model)
    restored = Envelope.model_validate_json(env.model_dump_json())
    return restored


def test_infocard_envelope_roundtrip() -> None:
    card = InfoCard(
        agent="market_data",
        kind=CardKind.MARKET,
        symbols=["600519.SH"],
        asof=utcnow(),
        source="mock",
        payload={"close": 1680.5, "rsi14": 55.2},
    )
    env = _roundtrip(card)
    assert env.type == "InfoCard"
    assert env.schema_version == 1
    back = env.unwrap(InfoCard)
    assert back.card_id == card.card_id
    assert back.payload["close"] == 1680.5


def test_decision_requires_size_for_non_hold() -> None:
    with pytest.raises(ValidationError, match="target_weight or qty"):
        Decision(symbol="600519.SH", action=Action.BUY)


def test_decision_hold_needs_no_size() -> None:
    d = Decision(symbol="600519.SH", action=Action.HOLD, rationale="flat")
    assert d.action is Action.HOLD


def test_limit_order_requires_price() -> None:
    with pytest.raises(ValidationError, match="limit_price"):
        OrderIntent(
            decision_id="dec_x",
            symbol="600519.SH",
            side=Side.BUY,
            qty=100,
            order_type=OrderType.LIMIT,
        )


def test_fill_and_risk_roundtrip() -> None:
    fill = FillReport(
        order_id="ord_1", status=FillStatus.FILLED, filled_qty=100, avg_price=12.3
    )
    assert _roundtrip(fill).unwrap(FillReport).status is FillStatus.FILLED

    evt = RiskEvent(level=RiskLevel.CRITICAL, code="PRICE_SPIKE", veto=True, symbols=["000001.SZ"])
    assert _roundtrip(evt).unwrap(RiskEvent).veto is True

    hb = Heartbeat(agent="market_data", metrics={"cards": 7})
    assert _roundtrip(hb).unwrap(Heartbeat).metrics["cards"] == 7


@pytest.mark.parametrize(
    "model",
    [
        InfoCard(agent="a", kind=CardKind.MARKET, asof=utcnow()),
        Decision(symbol="s", action=Action.HOLD),
        OrderIntent(decision_id="d", symbol="s", side=Side.BUY, qty=1),
        FillReport(order_id="o", status=FillStatus.REJECTED, filled_qty=0, avg_price=0),
        RiskEvent(level=RiskLevel.INFO, code="X"),
        Heartbeat(agent="a"),
    ],
)
def test_all_contracts_have_schema_version(model: BaseModel) -> None:
    assert model.schema_version == 1
