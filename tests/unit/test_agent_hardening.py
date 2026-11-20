"""AgentBase hardening — msg_id dedup + DLQ on handler faults."""

import pytest
from sqlalchemy import select

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.engine import init_db, session_factory
from quant_swarm.core.db.models import DLQRow
from quant_swarm.core.schemas import CtrlCommand
from quant_swarm.core.schemas.envelope import Envelope

SUBJ = "qs.test.input"


class CountingAgent(AgentBase):
    name = "counting"

    def __init__(self, *args, fail: bool = False, **kw) -> None:
        super().__init__(*args, **kw)
        self.received = 0
        self._fail = fail

    async def on_start(self) -> None:
        await self.subscribe(SUBJ, self._on_msg)

    async def _on_msg(self, msg):
        self.received += 1
        if self._fail:
            raise RuntimeError("boom")


@pytest.fixture
async def world(tmp_path):
    db = str(tmp_path / "h.db")
    await init_db(db)
    bus = LocalBus()
    yield bus, Settings(bus="local", db_path=db), AppConfig()


def _raw(env: Envelope) -> bytes:
    return env.model_dump_json().encode()


async def test_duplicate_msg_id_is_dropped(world) -> None:
    bus, settings, cfg = world
    agent = CountingAgent(bus, settings, cfg)
    await agent.start()

    env = Envelope.wrap(CtrlCommand(command="collect"))
    await bus.publish(SUBJ, _raw(env))
    await bus.publish(SUBJ, _raw(env))  # same msg_id -> deduped
    other = Envelope.wrap(CtrlCommand(command="decide"))
    await bus.publish(SUBJ, _raw(other))

    assert agent.received == 2
    assert agent._metrics["deduped"] == 1
    await agent.stop()


async def test_handler_fault_goes_to_dlq(world) -> None:
    bus, settings, cfg = world
    dlq_msgs = []

    async def _collect(m):
        dlq_msgs.append(m)

    await bus.subscribe(subjects.dlq("counting"), _collect)
    agent = CountingAgent(bus, settings, cfg, fail=True)
    await agent.start()

    env = Envelope.wrap(CtrlCommand(command="collect"), trace_id="t-dlq")
    await bus.publish(SUBJ, _raw(env))

    async with session_factory(settings.db_path)() as s:
        rows = (await s.execute(select(DLQRow))).scalars().all()
    assert len(rows) == 1
    assert rows[0].agent == "counting"
    assert rows[0].subject == SUBJ
    assert "boom" in rows[0].error
    assert rows[0].trace_id == "t-dlq"
    assert len(dlq_msgs) == 1
    assert agent._metrics["dlq"] == 1
    await agent.stop()


async def test_malformed_message_goes_to_dlq(world) -> None:
    bus, settings, cfg = world
    agent = CountingAgent(bus, settings, cfg)
    await agent.start()

    await bus.publish(SUBJ, b"not json at all")

    async with session_factory(settings.db_path)() as s:
        rows = (await s.execute(select(DLQRow))).scalars().all()
    assert len(rows) == 1
    assert "malformed" in rows[0].error
    assert agent.received == 0
    await agent.stop()
