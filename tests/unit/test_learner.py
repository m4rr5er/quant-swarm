"""LearnerService — observe -> reflect -> apply ops -> report."""

import asyncio
from types import SimpleNamespace
from typing import ClassVar

import pytest
from sqlalchemy import select

from quant_swarm.agents.learner.agent import LearnerService, LearnOutput, MemoryOp
from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AgentSpec, AppConfig, Settings
from quant_swarm.core.db.engine import init_db, session_factory
from quant_swarm.core.db.models import ReviewReportRow
from quant_swarm.core.memory import agent_memory, user_memory
from quant_swarm.core.schemas import CtrlCommand, ReviewReport


class ScriptedLearner:
    """Returns queued LearnOutputs; falls back to an empty model()."""

    def __init__(self, outputs: list) -> None:
        self.outputs = list(outputs)
        self.calls = 0

    class profile:
        model = "scripted"

    last_usage: ClassVar[dict] = {"total_tokens": 10}

    async def chat_structured(self, messages, model, **kw):
        self.calls += 1
        return self.outputs.pop(0) if self.outputs else model()


class ConsolidatingClient(ScriptedLearner):
    """Answers the consolidate call with compacted sections."""

    async def chat_structured(self, messages, model, **kw):
        self.calls += 1
        if self.outputs:
            return self.outputs.pop(0)
        return SimpleNamespace(sections={"已有": "压缩"})


@pytest.fixture
async def world(tmp_path):
    db = str(tmp_path / "l.db")
    await init_db(db)
    bus = LocalBus()
    settings = Settings(bus="local", db_path=db, memory_dir=str(tmp_path / "memory"))
    cfg = AppConfig(agents={"learner": AgentSpec(params={"interval_min": 0})})
    yield bus, settings, cfg
    await bus.close()


async def _run(bus, settings, cfg, client) -> LearnerService:
    svc = LearnerService(bus, settings, cfg, client=client)
    await svc.start()
    return svc


async def test_cycle_applies_ops_and_reports(world, monkeypatch, tmp_path) -> None:
    bus, settings, cfg = world
    monkeypatch.setattr(
        "quant_swarm.agents.learner.agent.skill_dir",
        lambda agent: tmp_path / "skills" / agent,
    )
    client = ScriptedLearner(
        [
            LearnOutput(
                summary="用户偏好短线",
                ops=[
                    MemoryOp(target="USER.md", title="偏好", body="关注短线"),
                    MemoryOp(
                        target="agents/market_data.md",
                        title="坑",
                        body="akshare 限频 3/s",
                    ),
                    MemoryOp(target="evil/escape.md", title="x", body="y"),
                ],
                skill_proposal={"agent": "quant", "content": "# 回测流程 v1\n先拉数据"},
            )
        ]
    )
    svc = await _run(bus, settings, cfg, client)
    reports = []
    await bus.subscribe(subjects.LEARN_REPORT, lambda m: reports.append(m.envelope()))
    await bus.publish_model(subjects.CTRL_LEARN, CtrlCommand(command="learn"))
    await asyncio.sleep(0.1)
    await svc.stop()

    assert len(reports) == 1
    rep = reports[0].unwrap(ReviewReport)
    assert rep.kind == "memory_update"
    assert "短线" in user_memory(settings.memory_dir).load()
    assert "限频" in agent_memory(settings.memory_dir, "market_data").load()
    assert (tmp_path / "skills" / "quant" / "proposed.md").exists()
    # bad target dropped
    assert not (tmp_path / "skills" / "evil").exists()

    sessions = session_factory(settings.db_path)
    async with sessions() as s:
        rows = (await s.execute(select(ReviewReportRow))).scalars().all()
    assert rows[0].summary == "用户偏好短线"


async def test_offline_cycle_is_harmless(world) -> None:
    bus, settings, cfg = world
    svc = await _run(bus, settings, cfg, client=None)
    reports = []
    await bus.subscribe(subjects.LEARN_REPORT, lambda m: reports.append(m.envelope()))
    await bus.publish_model(subjects.CTRL_LEARN, CtrlCommand(command="learn"))
    await asyncio.sleep(0.1)
    await svc.stop()
    rep = reports[0].unwrap(ReviewReport)
    assert rep.kind == "observation" and "offline" in rep.summary


async def test_memory_full_consolidates(world) -> None:
    bus, settings, cfg = world
    mf = user_memory(settings.memory_dir)
    mf.set("已有", "x" * 1300)  # near the 1400-char budget
    client = ConsolidatingClient([])
    svc = await _run(bus, settings, cfg, client)
    ok = await svc._apply_op(MemoryOp(target="USER.md", title="新", body="y" * 200))
    await svc.stop()
    assert ok is True
    text = mf.load()
    assert "压缩" in text and "新" in text and len(text) < 1400
