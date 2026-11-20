"""Offscreen widget smoke — MainWindow renders store state into tables."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", reason="PySide6 not installed")

from PySide6.QtWidgets import QApplication

from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.engine import init_db
from quant_swarm.core.schemas import (
    Action,
    AgentState,
    CardKind,
    Decision,
    Heartbeat,
    InfoCard,
    RiskEvent,
    RiskLevel,
)
from quant_swarm.core.timeutils import utcnow
from quant_swarm.ui.main_window import MainWindow
from quant_swarm.ui.store import DashboardStore


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


async def test_window_renders_store_state(qapp, tmp_path) -> None:
    db = str(tmp_path / "w.db")
    await init_db(db)
    store = DashboardStore(LocalBus(), Settings(bus="local", db_path=db), AppConfig())
    win = MainWindow(store)
    win.show()

    store.heartbeats["market_data"] = Heartbeat(
        agent="market_data", state=AgentState.RUNNING
    )
    store.cards.appendleft(
        InfoCard(
            agent="market_data",
            kind=CardKind.MARKET,
            symbols=["X"],
            asof=utcnow(),
            payload={"closes": [1.0]},
        )
    )
    store.decisions.appendleft(
        Decision(symbol="X", action=Action.HOLD, rationale="r")
    )
    store.risk_events.appendleft(
        RiskEvent(code="PRICE_SPIKE_DOWN", level=RiskLevel.CRITICAL, symbols=["X"])
    )
    win.refresh_all()

    assert win.tbl_agents.rowCount() == 1
    assert win.tbl_agents.item(0, 0).text() == "market_data"
    assert win.tbl_cards.rowCount() == 1
    assert win.tbl_decisions.rowCount() == 1
    assert win.tbl_decisions.item(0, 2).text() == "HOLD"
    assert win.tbl_risk.rowCount() == 1
    assert win.tbl_risk.item(0, 1).text() == "CRITICAL"
    win.close()
