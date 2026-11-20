"""Chat chain — user msg -> router -> ExpertTask -> expert reply -> db+FTS."""

import pytest
from sqlalchemy import select

from quant_swarm.chat.service import ChatService
from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.engine import init_db, session_factory
from quant_swarm.core.db.models import MessageRow, SessionRow
from quant_swarm.core.schemas import ChatChannel, ChatMessage, ChatRole, ExpertTask


@pytest.fixture
async def world(tmp_path):
    db = str(tmp_path / "chat.db")
    await init_db(db)
    bus = LocalBus()
    cfg = AppConfig()
    svc = ChatService(bus, Settings(bus="local", db_path=db), cfg)
    await svc.start()
    yield bus, svc, db
    await svc.stop()


async def test_user_msg_routes_to_quant(world) -> None:
    bus, _svc, db = world
    captured = []
    await bus.subscribe(subjects.expert_task("quant"), lambda m: captured.append(m))

    await bus.publish_model(
        subjects.CHAT_IN,
        ChatMessage(session_id="s1", role=ChatRole.USER, content="帮我回测双均线策略"),
    )
    assert len(captured) == 1
    task = captured[0].envelope().unwrap(ExpertTask)
    assert task.task == "帮我回测双均线策略"
    assert task.history and task.history[0]["role"] == ChatRole.USER

    sessions = session_factory(db)
    async with sessions() as s:
        sess = (await s.execute(select(SessionRow))).scalars().all()
        msgs = (await s.execute(select(MessageRow))).scalars().all()
    assert len(sess) == 1 and sess[0].session_id == "s1"
    assert len(msgs) == 1 and msgs[0].role == "user"


async def test_expert_reply_persisted_and_searchable(world) -> None:
    bus, _svc, db = world
    await bus.publish_model(
        subjects.chat_out("dashboard"),
        ChatMessage(
            session_id="s1",
            role=ChatRole.EXPERT,
            expert="investor",
            content="建议观望，茅台主力资金连续三日净流出",
            channel=ChatChannel.DASHBOARD,
        ),
    )
    sessions = session_factory(db)
    async with sessions() as s:
        msgs = (await s.execute(select(MessageRow))).scalars().all()
        # the search path experts use is CJK-safe LIKE over messages
        hits = (
            await s.execute(
                select(MessageRow).where(MessageRow.content.like("%茅台%"))
            )
        ).scalars().all()
    assert msgs[0].expert == "investor"
    assert len(hits) == 1
