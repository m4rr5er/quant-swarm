"""Crash supervision — failed components restart with backoff."""

import asyncio

import pytest

from quant_swarm.core.bus import LocalBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.runtime import supervise_component


class FlakyComponent:
    """Crashes on start ``fail_times`` times, then stops immediately."""

    name = "flaky"

    def __init__(self, counter: dict, fail_times: int) -> None:
        self._counter = counter
        self._fail_times = fail_times

    async def start(self) -> None:
        self._counter["starts"] = self._counter.get("starts", 0) + 1
        if self._counter["starts"] <= self._fail_times:
            raise RuntimeError("boom on start")

    async def wait_stopped(self) -> None:
        return

    async def stop(self) -> None:
        return


async def test_crashed_component_restarts(tmp_path) -> None:
    counter: dict = {}
    bus = LocalBus()
    settings = Settings(bus="local", db_path=str(tmp_path / "s.db"))
    attempts = {"n": 0}

    def factory(b, s, c):
        attempts["n"] += 1
        return FlakyComponent(counter, fail_times=2)

    restarts = await supervise_component(
        "flaky", factory, bus, settings, AppConfig(), max_backoff=0.01
    )
    assert restarts == 2
    assert attempts["n"] == 3  # initial + 2 restarts
    assert counter["starts"] == 3


async def test_clean_stop_returns_zero_restarts(tmp_path) -> None:
    bus = LocalBus()
    settings = Settings(bus="local", db_path=str(tmp_path / "s2.db"))

    def factory(b, s, c):
        return FlakyComponent({}, fail_times=0)

    restarts = await supervise_component("ok", factory, bus, settings, AppConfig())
    assert restarts == 0


async def test_cancel_propagates_and_stops(tmp_path) -> None:
    bus = LocalBus()
    settings = Settings(bus="local", db_path=str(tmp_path / "s3.db"))
    stopped = asyncio.Event()

    class Hanging(FlakyComponent):
        async def wait_stopped(self) -> None:
            await asyncio.Event().wait()

        async def stop(self) -> None:
            stopped.set()

    def factory(b, s, c):
        return Hanging({}, 0)

    task = asyncio.create_task(
        supervise_component("hang", factory, bus, settings, AppConfig())
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
