"""Execution risk veto — CRITICAL veto events reject matching orders."""

import pytest
from sqlalchemy import select

from quant_swarm.agents.execution.agent import ExecutionAgent
from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AgentSpec, AppConfig, Settings
from quant_swarm.core.db.engine import init_db, session_factory
from quant_swarm.core.db.models import OrderRow, PositionRow
from quant_swarm.core.schemas import (
    CardKind,
    FillReport,
    FillStatus,
    InfoCard,
    OrderIntent,
    RiskEvent,
    RiskLevel,
    Side,
)
from quant_swarm.core.timeutils import utcnow


@pytest.fixture
async def world(tmp_path):
    db = str(tmp_path / "v.db")
    await init_db(db)
    bus = LocalBus()
    fills: list[FillReport] = []

    async def on_fill(msg):
        fills.append(msg.envelope().unwrap(FillReport))

    await bus.subscribe(subjects.FILLS, on_fill)
    settings = Settings(bus="local", db_path=db)
    cfg = AppConfig(
        agents={"execution": AgentSpec(params={"veto_ttl_sec": 1800})}
    )
    agent = ExecutionAgent(bus, settings, cfg)
    await agent.start()
    yield bus, agent, fills, settings
    await agent.stop()


async def _prime_price(bus) -> None:
    await bus.publish_model(
        subjects.cards_market("X"),
        InfoCard(
            agent="market_data",
            kind=CardKind.MARKET,
            symbols=["X"],
            asof=utcnow(),
            payload={"closes": [100.0]},
        ),
    )


async def test_veto_rejects_order_for_symbol(world) -> None:
    bus, agent, fills, settings = world
    await _prime_price(bus)
    await bus.publish_model(
        subjects.ALERTS_EVENTS,
        RiskEvent(
            code="PRICE_SPIKE_DOWN",
            level=RiskLevel.CRITICAL,
            symbols=["X"],
            veto=True,
        ),
    )
    assert agent._vetoed("X") and not agent._vetoed("Y")

    await bus.publish_model(
        subjects.ORDERS,
        OrderIntent(decision_id="d1", symbol="X", side=Side.BUY, qty=100),
    )
    assert len(fills) == 1
    assert fills[0].status is FillStatus.REJECTED
    assert fills[0].meta["reason"] == "risk_veto"

    async with session_factory(settings.db_path)() as s:
        order = (await s.execute(select(OrderRow))).scalar_one()
        assert order.status == "REJECTED"
        positions = (await s.execute(select(PositionRow))).scalars().all()
        assert positions == []


async def test_veto_does_not_block_other_symbols(world) -> None:
    bus, _agent, fills, _ = world
    await _prime_price(bus)
    await bus.publish_model(
        subjects.ALERTS_EVENTS,
        RiskEvent(
            code="PRICE_SPIKE_DOWN",
            level=RiskLevel.CRITICAL,
            symbols=["X"],
            veto=True,
        ),
    )
    await bus.publish_model(
        subjects.ORDERS,
        OrderIntent(decision_id="d2", symbol="Y", side=Side.BUY, qty=100),
    )
    # no price for Y yet -> rejected by no_price, not by veto
    assert fills[0].status is FillStatus.REJECTED
    assert fills[0].meta["reason"] == "no_price"


async def test_warn_event_does_not_veto(world) -> None:
    bus, agent, _, _ = world
    await bus.publish_model(
        subjects.ALERTS_EVENTS,
        RiskEvent(code="PRICE_SPIKE_UP", level=RiskLevel.WARN, symbols=["X"]),
    )
    assert not agent._vetoed("X")


async def test_global_scope_veto_blocks_everything(world) -> None:
    bus, agent, _, _ = world
    await bus.publish_model(
        subjects.ALERTS_EVENTS,
        RiskEvent(
            code="FLASH_CRASH", level=RiskLevel.CRITICAL, scope="global", veto=True
        ),
    )
    assert agent._vetoed("X") and agent._vetoed("ANYTHING")
