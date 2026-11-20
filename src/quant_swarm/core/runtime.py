"""Component launcher — shared bootstrap for every agent/service process.

Loads settings + config, sets logging, connects the bus, ensures the DB
exists, runs the component until SIGINT, then stops it cleanly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from quant_swarm.core.bus import MessageBus, make_bus
from quant_swarm.core.config import AppConfig, Settings, load_config, load_settings
from quant_swarm.core.db.engine import init_db
from quant_swarm.core.logging import setup_logging


class Component:
    """Structural contract shared by AgentBase and SchedulerService."""

    name: str

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def wait_stopped(self) -> None: ...


Factory = Callable[[MessageBus, Settings, AppConfig], Component]


async def _serve(factory: Factory, name: str) -> None:
    settings = load_settings()
    setup_logging(name, settings.log_dir, settings.log_level)
    cfg = load_config(settings.config_dir)
    await init_db(settings.db_path)
    bus = make_bus(settings.bus, settings.nats_url)
    component = factory(bus, settings, cfg)
    try:
        await bus.connect()
        await component.start()
        await component.wait_stopped()
    finally:
        await component.stop()
        await bus.close()


async def _serve_all(factories: list[Factory]) -> None:
    settings = load_settings()
    setup_logging("all", settings.log_dir, settings.log_level)
    cfg = load_config(settings.config_dir)
    await init_db(settings.db_path)
    bus = make_bus(settings.bus, settings.nats_url)
    components = [f(bus, settings, cfg) for f in factories]
    try:
        await bus.connect()
        for c in components:
            await c.start()
        await asyncio.gather(*(c.wait_stopped() for c in components))
    finally:
        for c in components:
            await c.stop()
        await bus.close()


def launch(factory: Factory, name: str) -> None:
    """Blocking entry point for ``python -m <component>`` and ``qs run``."""
    try:
        asyncio.run(_serve(factory, name))
    except KeyboardInterrupt:
        pass


def launch_all(factories: list[Factory]) -> None:
    """All-in-one dev mode: every component as a task on one bus."""
    try:
        asyncio.run(_serve_all(factories))
    except KeyboardInterrupt:
        pass
