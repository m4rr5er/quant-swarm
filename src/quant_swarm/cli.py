"""qs — Quant$warm control CLI."""

from __future__ import annotations

import asyncio

import typer

from quant_swarm import __version__
from quant_swarm.core.config import load_config, load_settings

app = typer.Typer(help="Quant$warm control CLI", no_args_is_help=True)
run_app = typer.Typer(help="Run a component", no_args_is_help=True)
trigger_app = typer.Typer(help="Manually fire a control message", no_args_is_help=True)
app.add_typer(run_app, name="run")
app.add_typer(trigger_app, name="trigger")


def _named(name, cls):
    """Factory carrying the component name (crash-restart logs use it)."""

    def factory(b, s, c):
        return cls(b, s, c)

    factory.__name__ = name
    return factory


def _factories() -> dict:
    from quant_swarm.agents.capital_flow.agent import CapitalFlowAgent
    from quant_swarm.agents.event_monitor.agent import EventMonitorAgent
    from quant_swarm.agents.execution.agent import ExecutionAgent
    from quant_swarm.agents.fundamentals.agent import FundamentalsAgent
    from quant_swarm.agents.market_data.agent import MarketDataAgent
    from quant_swarm.brain.service import BrainService
    from quant_swarm.scheduler.service import SchedulerService

    return {
        "scheduler": _named("scheduler", SchedulerService),
        "market_data": _named("market_data", MarketDataAgent),
        "fundamentals": _named("fundamentals", FundamentalsAgent),
        "capital_flow": _named("capital_flow", CapitalFlowAgent),
        "event_monitor": _named("event_monitor", EventMonitorAgent),
        "brain": _named("brain", BrainService),
        "execution": _named("execution", ExecutionAgent),
    }


@app.command()
def version() -> None:
    """Print version."""
    typer.echo(__version__)


@app.command("init-db")
def init_db_cmd() -> None:
    """Create the SQLite operational store (all tables, WAL mode)."""
    from quant_swarm.core.db.engine import init_db

    settings = load_settings()
    asyncio.run(init_db(settings.db_path))
    typer.echo(f"database ready: {settings.db_path}")


@app.command()
def info() -> None:
    """Show resolved settings + business config summary."""
    settings = load_settings()
    cfg = load_config(settings.config_dir)
    typer.echo(f"bus            : {settings.bus} ({settings.nats_url})")
    typer.echo(f"db             : {settings.db_path}")
    typer.echo(f"logs           : {settings.log_dir} ({settings.log_level})")
    typer.echo(f"watchlist      : {', '.join(cfg.watchlist) or '(empty)'}")
    typer.echo(f"llm profiles   : {', '.join(cfg.llm.profiles) or '(none)'}")
    for name, spec in cfg.agents.items():
        state = "on " if spec.enabled else "off"
        typer.echo(f"agent {name:<14}: {state}")


@run_app.command("scheduler")
def _run_scheduler() -> None:
    from quant_swarm.core.runtime import launch

    launch(_factories()["scheduler"], "scheduler")


@run_app.command("agent")
def _run_agent(name: str) -> None:
    from quant_swarm.core.runtime import launch

    factory = _factories().get(name)
    if factory is None:
        raise typer.BadParameter(f"unknown agent {name!r} (have: {', '.join(_factories())})")
    launch(factory, name)


@run_app.command("brain")
def _run_brain() -> None:
    from quant_swarm.core.runtime import launch

    launch(_factories()["brain"], "brain")


@run_app.command("ui")
def _run_ui() -> None:
    """PySide6 dashboard — live view of bus + operational store."""
    from quant_swarm.ui.app import run

    raise SystemExit(run())


@run_app.command("all")
def _run_all() -> None:
    """All-in-one dev mode — every enabled component as tasks on one bus."""
    from quant_swarm.core.runtime import launch_all

    settings = load_settings()
    cfg = load_config(settings.config_dir)
    f = _factories()
    enabled = [f[name] for name in f if name == "scheduler" or cfg.agent(name).enabled]
    launch_all(enabled)


async def _fire(subject: str, model) -> None:
    from quant_swarm.core.bus import make_bus

    settings = load_settings()
    bus = make_bus(settings.bus, settings.nats_url)
    try:
        await bus.connect()
        await bus.publish_model(subject, model)
    finally:
        await bus.close()


@trigger_app.command("collect")
def _trigger_collect(agent: str = "market_data") -> None:
    """Publish qs.ctrl.collect.<agent> now."""
    from quant_swarm.core import subjects
    from quant_swarm.core.schemas import CtrlCommand

    asyncio.run(_fire(subjects.ctrl_collect(agent), CtrlCommand(command="collect")))
    typer.echo(f"fired collect -> {agent}")


@trigger_app.command("decide")
def _trigger_decide() -> None:
    """Publish qs.ctrl.decide now."""
    from quant_swarm.core import subjects
    from quant_swarm.core.schemas import CtrlCommand

    asyncio.run(_fire(subjects.CTRL_DECIDE, CtrlCommand(command="decide")))
    typer.echo("fired decide")


if __name__ == "__main__":
    app()
