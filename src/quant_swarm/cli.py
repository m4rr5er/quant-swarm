"""qs — Quant$warm control CLI."""

from __future__ import annotations

import asyncio

import typer

from quant_swarm import __version__
from quant_swarm.core.config import load_config, load_settings

app = typer.Typer(help="Quant$warm control CLI", no_args_is_help=True)
run_app = typer.Typer(help="Run a component", no_args_is_help=True)
app.add_typer(run_app, name="run")


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


def _stub(what: str) -> None:
    typer.echo(f"{what}: lands in M1 (contracts & infra only in M0)")


@run_app.command("scheduler")
def _run_scheduler() -> None:
    _stub("scheduler")


@run_app.command("agent")
def _run_agent(name: str) -> None:
    _stub(f"agent {name}")


@run_app.command("brain")
def _run_brain() -> None:
    _stub("brain")


@run_app.command("ui")
def _run_ui() -> None:
    _stub("ui")


@run_app.command("all")
def _run_all() -> None:
    _stub("all-in-one")


if __name__ == "__main__":
    app()
