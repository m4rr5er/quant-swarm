"""ExpertService — tool loop, acceptance, memory writes, reply publishing."""

import pytest

from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.engine import init_db
from quant_swarm.core.memory import expert_memory
from quant_swarm.core.schemas import ChatMessage, ExpertTask
from quant_swarm.experts.base import ExpertAction, ExpertService


class ScriptedClient:
    """Fake LLMClient — returns queued ExpertActions, repeating the last
    one when the queue runs dry (nudges consume extra calls)."""

    def __init__(self, actions: list[ExpertAction]) -> None:
        self.actions = actions
        self.calls = 0

    class profile:
        model = "scripted"

    async def chat_structured(self, messages, model, **kw):
        self.calls += 1
        assert model is ExpertAction
        return self.actions[min(self.calls, len(self.actions)) - 1]


@pytest.fixture
async def world(tmp_path):
    db = str(tmp_path / "x.db")
    await init_db(db)
    bus = LocalBus()
    settings = Settings(bus="local", db_path=db, memory_dir=str(tmp_path / "memory"))
    yield bus, settings
    await bus.close()


async def _run(bus, settings, client) -> ExpertService:
    svc = ExpertService(bus, settings, AppConfig(), expert_name="investor", client=client)
    await svc.start()
    return svc


async def test_reply_roundtrip(world) -> None:
    bus, settings = world
    client = ScriptedClient([ExpertAction(type="reply", content="建议观望")])
    svc = await _run(bus, settings, client)
    replies = []
    await bus.subscribe(
        subjects.chat_out("dashboard"), lambda m: replies.append(m.envelope())
    )
    await bus.publish_model(
        subjects.expert_task("investor"),
        ExpertTask(session_id="s1", task="茅台能加仓吗"),
        trace_id="tr-1",
    )
    await svc.stop()

    assert len(replies) == 1
    msg = replies[0].unwrap(ChatMessage)
    assert msg.expert == "investor" and msg.content == "建议观望"
    assert replies[0].trace_id == "tr-1"


async def test_tool_loop_then_reply(world) -> None:
    bus, settings = world
    client = ScriptedClient(
        [
            ExpertAction(type="tool", tool="read_portfolio", args={}),
            ExpertAction(
                type="tool",
                tool="memory",
                args={"action": "set", "title": "笔记", "body": "用户关注茅台"},
            ),
            ExpertAction(type="reply", content="目前空仓"),
        ]
    )
    svc = await _run(bus, settings, client)
    replies = []
    await bus.subscribe(subjects.chat_out("dashboard"), lambda m: replies.append(m))
    await bus.publish_model(
        subjects.expert_task("investor"),
        ExpertTask(session_id="s1", task="现在持仓情况"),
    )
    await svc.stop()

    assert client.calls == 3
    assert replies[0].envelope().unwrap(ChatMessage).content == "目前空仓"
    assert "茅台" in expert_memory(settings.memory_dir, "investor").load()


async def test_round_overflow_degrades(world) -> None:
    bus, settings = world
    client = ScriptedClient(
        [ExpertAction(type="tool", tool="read_risk_events", args={})] * 8
    )
    svc = await _run(bus, settings, client)
    replies = []
    await bus.subscribe(subjects.chat_out("dashboard"), lambda m: replies.append(m))
    await bus.publish_model(
        subjects.expert_task("investor"), ExpertTask(session_id="s1", task="x")
    )
    await svc.stop()
    assert "超出处理轮次" in replies[0].envelope().unwrap(ChatMessage).content


async def test_offline_replies_apology(world) -> None:
    bus, settings = world
    svc = await _run(bus, settings, client=None)
    replies = []
    await bus.subscribe(subjects.chat_out("dashboard"), lambda m: replies.append(m))
    await bus.publish_model(
        subjects.expert_task("investor"), ExpertTask(session_id="s1", task="hi")
    )
    await svc.stop()
    assert "离线" in replies[0].envelope().unwrap(ChatMessage).content
