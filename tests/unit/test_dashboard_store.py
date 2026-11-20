"""DashboardStore — bus->state fan-in + db fallback (headless)."""

import pytest

from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.engine import init_db
from quant_swarm.core.db.models import InfoCardRow
from quant_swarm.core.schemas import (
    Action,
    AgentState,
    CardKind,
    Decision,
    FillReport,
    FillStatus,
    Heartbeat,
    InfoCard,
    RiskEvent,
    RiskLevel,
)
from quant_swarm.core.timeutils import utcnow
from quant_swarm.ui.store import DashboardStore


@pytest.fixture
async def store(tmp_path):
    db = str(tmp_path / "ui.db")
    await init_db(db)
    bus = LocalBus()
    s = DashboardStore(bus, Settings(bus="local", db_path=db), AppConfig())
    hits = []
    s.on_change(lambda: hits.append(1))
    await s.start()
    yield bus, s, hits
    await s.stop()


async def test_fan_in_updates_state(store) -> None:
    bus, s, hits = store

    await bus.publish_model(
        subjects.heartbeat("market_data"),
        Heartbeat(agent="market_data", state=AgentState.RUNNING, metrics={"cards": 3}),
    )
    await bus.publish_model(
        subjects.cards_market("X"),
        InfoCard(
            agent="market_data",
            kind=CardKind.MARKET,
            symbols=["X"],
            asof=utcnow(),
            payload={"closes": [1.0, 2.0]},
        ),
    )
    await bus.publish_model(
        subjects.DECISIONS,
        Decision(symbol="X", action=Action.BUY, qty=100, rationale="r"),
    )
    await bus.publish_model(
        subjects.FILLS,
        FillReport(order_id="o1", status=FillStatus.FILLED, filled_qty=100, avg_price=2.0),
    )
    await bus.publish_model(
        subjects.ALERTS_EVENTS,
        RiskEvent(code="PRICE_SPIKE_UP", level=RiskLevel.WARN, symbols=["X"]),
    )

    assert s.heartbeats["market_data"].metrics["cards"] == 3
    assert s.cards[0].symbols == ["X"]
    assert s.decisions[0].action is Action.BUY
    assert s.fills[0].filled_qty == 100
    assert s.risk_events[0].code == "PRICE_SPIKE_UP"
    assert len(hits) == 5  # one notify per message


async def test_card_detail_prefers_memory(store) -> None:
    bus, s, _ = store
    card = InfoCard(
        card_id="card_mem",
        agent="t",
        kind=CardKind.MARKET,
        symbols=["X"],
        asof=utcnow(),
        payload={"closes": [9.0]},
    )
    await bus.publish_model(subjects.cards_market("X"), card)
    detail = await s.card_detail("card_mem")
    assert detail["payload"] == {"closes": [9.0]}


async def test_card_detail_falls_back_to_db(store) -> None:
    _bus, s, _ = store
    async with s.sessions() as sess:
        sess.add(
            InfoCardRow(
                card_id="card_db",
                agent="t",
                kind="fundamental",
                symbols=["Y"],
                asof=utcnow(),
                received_ts=utcnow(),
                payload={"snapshot": {"行业": "银行"}},
            )
        )
        await sess.commit()
    detail = await s.card_detail("card_db")
    assert detail["kind"] == "fundamental"
    assert detail["payload"]["snapshot"]["行业"] == "银行"
    assert await s.card_detail("missing") is None
