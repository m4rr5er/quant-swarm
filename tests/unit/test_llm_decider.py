"""LLM decider — prompt shape + structured output plumbing (fake client)."""

import json
from types import SimpleNamespace

from quant_swarm.brain.llm_decider import LLMDecider, LLMDecisionOut, build_messages
from quant_swarm.core.schemas import Action, CardKind, InfoCard, RiskEvent, RiskLevel
from quant_swarm.core.timeutils import utcnow


class FakeClient:
    """Duck-typed LLMClient stand-in: records messages, returns a fixed out."""

    def __init__(self, out: LLMDecisionOut) -> None:
        self.out = out
        self.profile = SimpleNamespace(model="fake-model")
        self.last_usage = {"total_tokens": 42}
        self.seen_messages: list = []

    async def chat_structured(self, messages, model, **kw):
        self.seen_messages.append(messages)
        return self.out


def _market_card() -> InfoCard:
    return InfoCard(
        agent="market_data",
        kind=CardKind.MARKET,
        symbols=["X"],
        asof=utcnow(),
        payload={
            "closes": [100.0, 101.0, 130.0],
            "indicators": {"ma5": 110.0, "ma20": 101.0},
        },
    )


def _capital_card() -> InfoCard:
    return InfoCard(
        agent="capital_flow",
        kind=CardKind.CAPITAL,
        symbols=["X"],
        asof=utcnow(),
        payload={"fund_flow": [{"主力净流入-净额": 1.2e8}]},
    )


def test_build_messages_carries_context() -> None:
    event = RiskEvent(code="PRICE_SPIKE_UP", level=RiskLevel.WARN, symbols=["X"])
    msgs = build_messages(
        symbol="X",
        market_card=_market_card(),
        extra_cards=[_capital_card()],
        position_qty=300,
        equity=100_000.0,
        max_weight=0.2,
        risk_events=[event],
    )
    assert msgs[0]["role"] == "system"
    ctx = json.loads(msgs[1]["content"].split("\n", 1)[1])
    assert ctx["symbol"] == "X"
    assert ctx["position_qty"] == 300
    assert ctx["max_weight"] == 0.2
    kinds = [c["kind"] for c in ctx["cards"]]
    assert kinds == ["market", "capital"]
    market = ctx["cards"][0]
    assert market["last_close"] == 130.0
    assert market["indicators"]["ma5"] == 110.0
    assert ctx["risk_events"][0]["code"] == "PRICE_SPIKE_UP"


async def test_decider_returns_structured_out() -> None:
    out = LLMDecisionOut(action=Action.BUY, target_weight=0.15, rationale="cross", confidence=0.7)
    decider = LLMDecider(FakeClient(out))  # type: ignore[arg-type]
    got = await decider.decide(
        symbol="X",
        market_card=_market_card(),
        extra_cards=[],
        position_qty=0,
        equity=100_000.0,
        max_weight=0.2,
        risk_events=[],
    )
    assert got is out
    assert got.action is Action.BUY and got.target_weight == 0.15
