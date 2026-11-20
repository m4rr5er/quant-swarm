"""LocalBus behaviour — deterministic inline delivery, NATS-like semantics."""

import asyncio

import pytest

from quant_swarm.core.bus import LocalBus
from quant_swarm.core.schemas import CardKind, InfoCard
from quant_swarm.core.timeutils import utcnow


async def test_publish_delivers_to_matching_sub() -> None:
    bus = LocalBus()
    got: list[tuple[str, bytes]] = []

    async def handler(msg):
        got.append((msg.subject, msg.data))

    await bus.subscribe("qs.cards.>", handler)
    await bus.publish("qs.cards.market.600519.SH", b'{"x":1}')
    await bus.publish("qs.other", b"skip")

    assert len(got) == 1
    assert got[0][0] == "qs.cards.market.600519.SH"


async def test_queue_group_gets_one_member_round_robin() -> None:
    bus = LocalBus()
    hits = {"a": 0, "b": 0}

    async def ha(msg):
        hits["a"] += 1

    async def hb(msg):
        hits["b"] += 1

    await bus.subscribe("qs.decisions", ha, queue_group="workers")
    await bus.subscribe("qs.decisions", hb, queue_group="workers")

    for _ in range(4):
        await bus.publish("qs.decisions", b"d")

    assert hits == {"a": 2, "b": 2}


async def test_plain_and_grouped_subs_both_receive() -> None:
    bus = LocalBus()
    got = {"plain": 0, "grouped": 0}

    async def plain(msg):
        got["plain"] += 1

    async def grouped(msg):
        got["grouped"] += 1

    await bus.subscribe("qs.decisions", plain)
    await bus.subscribe("qs.decisions", grouped, queue_group="w")
    await bus.publish("qs.decisions", b"d")

    assert got == {"plain": 1, "grouped": 1}


async def test_request_reply() -> None:
    bus = LocalBus()

    async def responder(msg):
        await msg.respond(b"pong")

    await bus.subscribe("qs.ctrl.decide", responder)
    assert await bus.request("qs.ctrl.decide", b"ping") == b"pong"


async def test_request_times_out_without_responder() -> None:
    bus = LocalBus()
    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await bus.request("qs.ctrl.decide", b"ping", timeout=0.05)


async def test_publish_model_roundtrip_through_envelope() -> None:
    bus = LocalBus()
    got = []

    async def handler(msg):
        got.append(msg.envelope().unwrap(InfoCard))

    await bus.subscribe("qs.cards.>", handler)
    card = InfoCard(agent="market_data", kind=CardKind.MARKET, asof=utcnow(), symbols=["s"])
    env = await bus.publish_model("qs.cards.market.s", card, trace_id="trace_1")

    assert got[0].card_id == card.card_id
    assert env.trace_id == "trace_1"


async def test_unsubscribe_stops_delivery() -> None:
    bus = LocalBus()
    got = []

    async def handler(msg):
        got.append(msg)

    sub = await bus.subscribe("qs.x", handler)
    await bus.publish("qs.x", b"1")
    await sub.unsubscribe()
    await bus.publish("qs.x", b"2")

    assert len(got) == 1


async def test_handler_crash_does_not_break_bus() -> None:
    bus = LocalBus()
    got = []

    async def bad(msg):
        raise RuntimeError("boom")

    async def good(msg):
        got.append(msg)

    await bus.subscribe("qs.x", bad)
    await bus.subscribe("qs.x", good)
    await bus.publish("qs.x", b"d")

    assert len(got) == 1
