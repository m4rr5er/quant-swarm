"""PaperBroker — fills, cash/position ledger, rejections."""

import pytest
from sqlalchemy import select

from quant_swarm.agents.execution.broker.paper import PaperBroker
from quant_swarm.core.db.engine import init_db, session_factory
from quant_swarm.core.db.models import AccountRow, PositionRow
from quant_swarm.core.schemas import FillStatus, OrderIntent, Side


@pytest.fixture
async def broker(tmp_path):
    db = str(tmp_path / "t.db")
    await init_db(db)
    return PaperBroker(session_factory(db), initial_cash=100_000.0), session_factory(db)


def _order(side: Side, qty: int) -> OrderIntent:
    return OrderIntent(decision_id="d", symbol="X", side=side, qty=qty)


async def test_buy_fills_and_updates_ledger(broker) -> None:
    b, sessions = broker
    fill = await b.place(_order(Side.BUY, 100), price=50.0)
    assert fill.status is FillStatus.FILLED and fill.avg_price == 50.0

    async with sessions() as s:
        pos = (await s.execute(select(PositionRow))).scalar_one()
        acc = (await s.execute(select(AccountRow))).scalar_one()
        assert pos.qty == 100 and pos.avg_cost == 50.0
        assert acc.cash == 100_000.0 - 5000.0


async def test_avg_cost_on_second_buy(broker) -> None:
    b, sessions = broker
    await b.place(_order(Side.BUY, 100), price=50.0)
    await b.place(_order(Side.BUY, 100), price=60.0)
    async with sessions() as s:
        pos = (await s.execute(select(PositionRow))).scalar_one()
        assert pos.qty == 200 and pos.avg_cost == 55.0


async def test_sell_realizes_pnl(broker) -> None:
    b, sessions = broker
    await b.place(_order(Side.BUY, 100), price=50.0)
    fill = await b.place(_order(Side.SELL, 100), price=60.0)
    assert fill.status is FillStatus.FILLED

    async with sessions() as s:
        pos = (await s.execute(select(PositionRow))).scalar_one()
        acc = (await s.execute(select(AccountRow))).scalar_one()
        assert pos.qty == 0 and pos.realized_pnl == 1000.0
        assert acc.cash == 100_000.0 + 1000.0


async def test_buy_rejected_when_cash_short(broker) -> None:
    b, _ = broker
    fill = await b.place(_order(Side.BUY, 10_000), price=50.0)
    assert fill.status is FillStatus.REJECTED
    assert fill.meta["reason"] == "insufficient_cash"


async def test_sell_rejected_without_position(broker) -> None:
    b, _ = broker
    fill = await b.place(_order(Side.SELL, 100), price=50.0)
    assert fill.status is FillStatus.REJECTED
    assert fill.meta["reason"] == "insufficient_position"


async def test_rejected_when_price_missing(broker) -> None:
    b, _ = broker
    fill = await b.place(_order(Side.BUY, 100), price=None)
    assert fill.status is FillStatus.REJECTED
    assert fill.meta["reason"] == "no_price"
