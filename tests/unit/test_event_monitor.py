"""Event monitor — reactive spike detection on market cards."""

import pytest

from quant_swarm.agents.event_monitor.agent import EventMonitorAgent, day_change
from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AgentSpec, AppConfig, Settings
from quant_swarm.core.db.engine import init_db
from quant_swarm.core.schemas import CardKind, InfoCard, RiskEvent, RiskLevel
from quant_swarm.core.timeutils import utcnow


def _card(closes: list[float], symbol: str = "X") -> InfoCard:
    return InfoCard(
        agent="market_data",
        kind=CardKind.MARKET,
        symbols=[symbol],
        asof=utcnow(),
        payload={"closes": closes},
    )


def test_day_change() -> None:
    assert day_change(_card([100.0, 105.0])) == pytest.approx(0.05)
    assert day_change(_card([100.0, 91.0])) == pytest.approx(-0.09)
    assert day_change(_card([100.0])) is None
    assert day_change(_card([])) is None


@pytest.fixture
async def monitor(tmp_path):
    db = str(tmp_path / "em.db")
    await init_db(db)
    bus = LocalBus()
    cfg = AppConfig(
        agents={"event_monitor": AgentSpec(params={"spike_pct": 0.05, "critical_pct": 0.09})}
    )
    agent = EventMonitorAgent(bus, Settings(bus="local", db_path=db), cfg)
    events: list[RiskEvent] = []

    async def on_event(msg):
        events.append(msg.envelope().unwrap(RiskEvent))

    await bus.subscribe(subjects.ALERTS_EVENTS, on_event)
    await agent.start()
    yield bus, events
    await agent.stop()


async def test_warn_spike_emits_risk_event(monitor) -> None:
    bus, events = monitor
    await bus.publish_model(subjects.cards_market("X"), _card([100.0, 106.0]))
    assert len(events) == 1
    e = events[0]
    assert e.code == "PRICE_SPIKE_UP"
    assert e.level is RiskLevel.WARN
    assert e.veto is False
    assert "6.00%" in e.message


async def test_critical_down_spike_vetoes(monitor) -> None:
    bus, events = monitor
    await bus.publish_model(subjects.cards_market("X"), _card([100.0, 90.0]))
    assert len(events) == 1
    e = events[0]
    assert e.code == "PRICE_SPIKE_DOWN"
    assert e.level is RiskLevel.CRITICAL
    assert e.veto is True


async def test_small_moves_stay_quiet(monitor) -> None:
    bus, events = monitor
    await bus.publish_model(subjects.cards_market("X"), _card([100.0, 102.0]))
    await bus.publish_model(subjects.cards_market("X"), _card([100.0, 95.5]))
    assert events == []
