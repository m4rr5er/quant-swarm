"""uiweb server — snapshot payload + chat post -> qs.chat.in."""

import httpx
import pytest

from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.engine import init_db
from quant_swarm.core.schemas import ChatMessage
from quant_swarm.uiweb.server import create_app
from quant_swarm.uiweb.store import DashboardStore


@pytest.fixture
async def client(tmp_path):
    db = str(tmp_path / "w.db")
    await init_db(db)
    bus = LocalBus()
    store = DashboardStore(bus, Settings(bus="local", db_path=db), AppConfig())
    app = create_app(store)
    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://t"), bus
    await bus.close()


async def test_snapshot_shape(client) -> None:
    http, _ = client
    data = (await http.get("/api/snapshot")).json()
    for key in (
        "agents", "cards", "decisions", "fills", "risk", "chat",
        "chat_session_id", "positions", "reports",
    ):
        assert key in data


async def test_chat_post_reaches_bus(client) -> None:
    http, bus = client
    inbox = []
    await bus.subscribe(subjects.CHAT_IN, lambda m: inbox.append(m.envelope()))
    resp = await http.post("/api/chat", json={"text": "看看茅台"})
    assert resp.status_code == 200
    assert inbox and inbox[0].unwrap(ChatMessage).content == "看看茅台"


async def test_index_and_static(client) -> None:
    http, _ = client
    assert (await http.get("/")).status_code == 200
    assert (await http.get("/static/app.css")).status_code == 200


async def test_files_endpoint(client) -> None:
    http, _ = client
    assert (await http.get("/api/files")).status_code == 200
