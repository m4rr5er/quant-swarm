"""BacktesterAgent — ctrl -> BACKTEST card on bus + persisted."""

import pytest
from sqlalchemy import select

from quant_swarm.agents.backtester.agent import BacktesterAgent
from quant_swarm.agents.market_data.providers.mock import MockMarketProvider
from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AgentSpec, AppConfig, Settings
from quant_swarm.core.db.engine import init_db, session_factory
from quant_swarm.core.db.models import InfoCardRow
from quant_swarm.core.schemas import CardKind, CtrlCommand, InfoCard


def _wave() -> list[float]:
    prices, p = [], 100.0
    for i in range(40):
        p += -3.0 if i < 15 or i >= 30 else 3.0
        prices.append(round(p, 2))
    return prices


@pytest.fixture
async def world(tmp_path):
    db = str(tmp_path / "bt.db")
    await init_db(db)
    bus = LocalBus()
    cfg = AppConfig(agents={"backtester": AgentSpec(provider="mock", params={"n_bars": 40})})
    agent = BacktesterAgent(bus, Settings(bus="local", db_path=db), cfg)
    agent.provider = MockMarketProvider(closes={"600519.SH": _wave()})
    await agent.start()
    yield bus, db
    await agent.stop()
    await bus.close()


async def _cards(bus):
    cards = []

    async def h(m):
        cards.append(m.envelope().unwrap(InfoCard))

    await bus.subscribe(subjects.CARDS_BACKTEST, h)
    return cards


async def test_backtest_card(world) -> None:
    bus, db = world
    cards = await _cards(bus)
    await bus.publish_model(
        subjects.CTRL_BACKTEST,
        CtrlCommand(
            command="backtest",
            args={
                "symbol": "600519.SH",
                "strategy": "ma_cross",
                "params": {"short": 3, "long": 8},
            },
        ),
    )
    assert len(cards) == 1
    card = cards[0]
    assert card.kind == CardKind.BACKTEST
    assert card.payload["n_bars"] == 40
    assert card.payload["stats"]["n_round_trips"] >= 1
    assert card.payload["trades"]

    sessions = session_factory(db)
    async with sessions() as s:
        rows = (await s.execute(select(InfoCardRow))).scalars().all()
    assert rows[0].kind == "backtest"


async def test_unknown_strategy_is_noop(world) -> None:
    bus, _ = world
    cards = await _cards(bus)
    await bus.publish_model(
        subjects.CTRL_BACKTEST,
        CtrlCommand(command="backtest", args={"symbol": "X", "strategy": "nope"}),
    )
    assert cards == []
