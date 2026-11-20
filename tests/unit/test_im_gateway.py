"""TelegramGateway — TG updates <-> qs.chat.* bridge (fake client)."""

import asyncio

import pytest

from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AgentSpec, AppConfig, Settings
from quant_swarm.core.db.engine import init_db
from quant_swarm.core.schemas import ChatChannel, ChatMessage, ChatRole
from quant_swarm.im.telegram import TelegramGateway


class FakeTG:
    def __init__(self, updates: list[dict]) -> None:
        self.updates = list(updates)
        self.sent: list[tuple[int | str, str]] = []
        self.actions = 0

    async def get_updates(self, offset: int, poll_timeout: int = 30) -> list[dict]:
        out, self.updates = self.updates, []
        return out

    async def send(self, chat_id: int | str, text: str) -> None:
        self.sent.append((chat_id, text))

    async def send_chat_action(self, chat_id: int | str, action: str = "typing") -> None:
        self.actions += 1


@pytest.fixture
async def world(tmp_path):
    db = str(tmp_path / "im.db")
    await init_db(db)
    bus = LocalBus()
    cfg = AppConfig(agents={"im_telegram": AgentSpec()})
    yield bus, db, cfg
    await bus.close()


def _update(text: str, chat_id: int = 42, upd_id: int = 1) -> dict:
    return {
        "update_id": upd_id,
        "message": {"text": text, "chat": {"id": chat_id, "type": "private"}},
    }


async def test_inbound_message_becomes_chat(world) -> None:
    bus, _, cfg = world
    gw = TelegramGateway(bus, Settings(bus="local"), cfg, client=FakeTG([_update("看看茅台")]))
    inbox = []
    await bus.subscribe(subjects.CHAT_IN, lambda m: inbox.append(m.envelope()))
    await gw.start()
    await asyncio.sleep(0.05)  # let the poll task consume the update
    await gw.stop()

    assert len(inbox) == 1
    chat = inbox[0].unwrap(ChatMessage)
    assert chat.session_id == "tg-42"
    assert chat.channel == ChatChannel.TELEGRAM
    assert chat.content == "看看茅台"


async def test_outbound_reply_goes_back(world) -> None:
    bus, _, cfg = world
    fake = FakeTG([])
    gw = TelegramGateway(bus, Settings(bus="local"), cfg, client=fake)
    await gw.start()
    await bus.publish_model(
        subjects.chat_out("telegram"),
        ChatMessage(
            session_id="tg-42",
            role=ChatRole.EXPERT,
            expert="quant",
            channel=ChatChannel.TELEGRAM,
            content="结论：不买",
        ),
    )
    await asyncio.sleep(0.05)
    await gw.stop()
    assert fake.sent == [(42, "【quant】\n结论：不买")]


async def test_nontext_and_foreign_session_ignored(world) -> None:
    bus, _, cfg = world
    fake = FakeTG(
        [
            {"update_id": 1, "message": {"chat": {"id": 42}}},  # no text
            {"update_id": 2, "edited_message": {"text": "x"}},
        ]
    )
    gw = TelegramGateway(bus, Settings(bus="local"), cfg, client=fake)
    inbox = []
    await bus.subscribe(subjects.CHAT_IN, lambda m: inbox.append(m.envelope()))
    await gw.start()
    # reply bound to a dashboard session must not leak to telegram
    await bus.publish_model(
        subjects.chat_out("telegram"),
        ChatMessage(session_id="sess-dashboard", role=ChatRole.EXPERT, content="x"),
    )
    await asyncio.sleep(0.05)
    await gw.stop()
    assert inbox == []
    assert fake.sent == []
