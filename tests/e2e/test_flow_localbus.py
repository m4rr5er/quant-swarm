"""M1 vertical slice — full chain on LocalBus.

scheduler trigger -> market_data collects + persists cards -> brain decides
(rule policy) -> execution paper-fills + updates positions/account, all
messages observed on the bus.
"""

import pytest
from sqlalchemy import select

from quant_swarm.agents.execution.agent import ExecutionAgent
from quant_swarm.agents.market_data.agent import MarketDataAgent
from quant_swarm.agents.market_data.providers.mock import MockMarketProvider
from quant_swarm.brain.service import BrainService
from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AccountSettings, AgentSpec, AppConfig, RiskSettings, Settings
from quant_swarm.core.db.engine import init_db
from quant_swarm.core.db.models import (
    AccountRow,
    DecisionRow,
    FillRow,
    InfoCardRow,
    OrderRow,
    PositionRow,
)
from quant_swarm.core.schemas import (
    Action,
    CtrlCommand,
    Decision,
    FillReport,
    FillStatus,
    OrderIntent,
)

WATCH = ["X"]


def _cfg() -> AppConfig:
    return AppConfig(
        watchlist=WATCH,
        risk=RiskSettings(max_position_weight=0.5),
        account=AccountSettings(initial_cash=100_000.0),
        agents={"market_data": AgentSpec(provider="mock")},
    )


@pytest.fixture
async def world(tmp_path):
    db = str(tmp_path / "e2e.db")
    await init_db(db)
    bus = LocalBus()
    settings = Settings(bus="local", db_path=db)
    cfg = _cfg()

    # scripted closes: flat -> last-bar spike forces a golden cross
    provider = MockMarketProvider(closes={"X": [100.0] * 24 + [130.0]})
    components = [
        MarketDataAgent(bus, settings, cfg, provider=provider),
        BrainService(bus, settings, cfg),
        ExecutionAgent(bus, settings, cfg),
    ]
    for c in components:
        await c.start()

    seen = {"decisions": [], "orders": [], "fills": []}

    async def collect(key, model):
        async def h(msg):
            seen[key].append(msg.envelope().unwrap(model))

        return h

    await bus.subscribe(subjects.DECISIONS, await collect("decisions", Decision))
    await bus.subscribe(subjects.ORDERS, await collect("orders", OrderIntent))
    await bus.subscribe(subjects.FILLS, await collect("fills", FillReport))

    yield bus, settings, seen
    for c in components:
        await c.stop()


async def test_full_chain_collect_to_fill(world) -> None:
    bus, settings, seen = world

    await bus.publish_model(
        subjects.ctrl_collect("market_data"), CtrlCommand(command="collect"), trace_id="t1"
    )
    await bus.publish_model(subjects.CTRL_DECIDE, CtrlCommand(command="decide"), trace_id="t1")

    # -- bus observations --
    assert len(seen["decisions"]) == 1
    decision = seen["decisions"][0]
    assert decision.action is Action.BUY
    assert decision.qty == 300  # 50% of 100k equity / 130 = 384 -> 300 shares

    assert len(seen["orders"]) == 1
    order = seen["orders"][0]
    assert order.qty == 300 and order.decision_id == decision.decision_id

    assert len(seen["fills"]) == 1
    fill = seen["fills"][0]
    assert fill.status is FillStatus.FILLED and fill.filled_qty == 300
    assert fill.avg_price == 130.0  # last close from the card

    # -- persistence --
    from quant_swarm.core.db.engine import session_factory

    async with session_factory(settings.db_path)() as s:
        cards = (await s.execute(select(InfoCardRow))).scalars().all()
        decisions = (await s.execute(select(DecisionRow))).scalars().all()
        orders = (await s.execute(select(OrderRow))).scalars().all()
        fills = (await s.execute(select(FillRow))).scalars().all()
        pos = (await s.execute(select(PositionRow))).scalar_one()
        acc = (await s.execute(select(AccountRow))).scalar_one()

    assert len(cards) == 1 and cards[0].trace_id == "t1"
    assert len(decisions) == 1 and decisions[0].action == "BUY"
    assert len(orders) == 1 and orders[0].status == "FILLED"
    assert len(fills) == 1
    assert pos.qty == 300
    assert acc.cash == pytest.approx(100_000.0 - 300 * 130.0)


async def test_hold_produces_decision_but_no_order(world) -> None:
    bus, _settings, seen = world

    # Publish a flat market card for a second symbol ourselves -> no cross,
    # so the brain emits HOLD and no OrderIntent.
    from quant_swarm.core.schemas import CardKind, InfoCard
    from quant_swarm.core.timeutils import utcnow

    flat_card = InfoCard(
        agent="market_data",
        kind=CardKind.MARKET,
        symbols=["Y"],
        asof=utcnow(),
        payload={"closes": [100.0] * 30},
    )
    await bus.publish_model(subjects.cards_market("Y"), flat_card, trace_id="t2")
    await bus.publish_model(subjects.CTRL_DECIDE, CtrlCommand(command="decide"), trace_id="t2")

    y_decisions = [d for d in seen["decisions"] if d.symbol == "Y"]
    assert len(y_decisions) == 1
    assert y_decisions[0].action is Action.HOLD
    assert not [o for o in seen["orders"] if o.symbol == "Y"]
