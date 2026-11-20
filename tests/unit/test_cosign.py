"""Co-signing — compound task -> two expert opinions -> primary synthesis."""

import pytest

from quant_swarm.chat.service import ChatService
from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.engine import init_db
from quant_swarm.core.schemas import ChatMessage, ChatRole, ExpertTask


@pytest.fixture
async def world(tmp_path):
    db = str(tmp_path / "cs.db")
    await init_db(db)
    bus = LocalBus()
    svc = ChatService(bus, Settings(bus="local", db_path=db), AppConfig())
    await svc.start()
    yield bus, svc
    await svc.stop()
    await bus.close()


async def _cap_tasks(bus):
    tasks = []

    async def cap(name):
        async def h(m):
            tasks.append((name, m.envelope().unwrap(ExpertTask)))

        await bus.subscribe(subjects.expert_task(name), h)

    await cap("investor")
    await cap("quant")
    return tasks


async def test_compound_dispatches_both_experts(world) -> None:
    bus, _ = world
    tasks = await _cap_tasks(bus)
    await bus.publish_model(
        subjects.CHAT_IN,
        ChatMessage(
            session_id="s1",
            role=ChatRole.USER,
            content="这个仓位的双均线策略信号可靠吗，要减仓吗",
        ),
    )
    assert {n for n, _ in tasks} == {"investor", "quant"}
    primaries = {t.context["primary"] for _, t in tasks}
    assert len(primaries) == 1 and primaries.pop() in ("investor", "quant")
    for name, t in tasks:
        assert t.context["cosign_role"] == "opinion"
        assert name in t.context["reply_subject"]


async def test_opinions_trigger_synthesis_to_primary(world) -> None:
    bus, _ = world
    tasks = await _cap_tasks(bus)
    await bus.publish_model(
        subjects.CHAT_IN,
        ChatMessage(session_id="s1", role=ChatRole.USER, content="仓位策略信号可靠吗要减仓吗"),
    )
    assert len(tasks) == 2
    group = tasks[0][1].context["cosign_group"]

    await bus.publish_model(
        subjects.cosign(group, "investor"),
        ChatMessage(
            session_id="s1", role=ChatRole.EXPERT, expert="investor", content="减仓一半"
        ),
    )
    await bus.publish_model(
        subjects.cosign(group, "quant"),
        ChatMessage(
            session_id="s1", role=ChatRole.EXPERT, expert="quant", content="信号胜率62%可持有"
        ),
    )

    assert len(tasks) == 3
    name, synth = tasks[-1]
    assert name == tasks[0][1].context["primary"]
    assert synth.context["cosign_role"] == "synthesis"
    assert "减仓一半" in synth.task and "62%" in synth.task
    assert "reply_subject" not in synth.context  # synthesis answers the user directly
