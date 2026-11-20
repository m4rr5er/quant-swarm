"""Local web dashboard server.

``qs run ui`` starts uvicorn on 127.0.0.1:<port> and opens the default
browser. The SPA polls ``/api/snapshot`` — every field the old Qt
dashboard showed is in that one payload.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from quant_swarm.core.bus import make_bus
from quant_swarm.core.config import load_config, load_settings
from quant_swarm.core.logging import setup_logging
from quant_swarm.uiweb.store import DashboardStore

STATIC = Path(__file__).parent / "static"


def _rows(objs: list | Any) -> list[dict]:
    """pydantic models -> json-safe dicts; orm rows -> column dicts."""
    out = []
    for o in objs:
        if hasattr(o, "model_dump"):
            out.append(o.model_dump(mode="json"))
        else:
            out.append(
                {k: v for k, v in vars(o).items() if not k.startswith("_")}
            )
    return out


class ChatIn(BaseModel):
    text: str


def create_app(store: DashboardStore) -> FastAPI:
    app = FastAPI(title="Quant$warm")

    @app.get("/api/snapshot")
    async def snapshot() -> JSONResponse:
        acc = await store.account()
        positions = await store.positions()
        reports = await store.learning_reports()
        return JSONResponse(
            jsonable_encoder({
                "agents": _rows(list(store.heartbeats.values())),
                "cards": _rows(list(store.cards)),
                "decisions": _rows(list(store.decisions)),
                "fills": _rows(list(store.fills)),
                "risk": _rows(list(store.risk_events)),
                "chat": _rows(list(store.chat)),
                "chat_session_id": store.chat_session_id,
                "account": _rows([acc])[0] if acc else None,
                "positions": _rows(positions),
                "reports": _rows(reports),
                "watchlist": list(store.cfg.watchlist),
            })
        )

    @app.get("/api/files")
    async def files() -> JSONResponse:
        return JSONResponse(store.learning_files())

    @app.get("/api/card/{card_id}")
    async def card(card_id: str) -> JSONResponse:
        detail = await store.card_detail(card_id)
        return JSONResponse(detail or {"error": "not found"}, status_code=200)

    @app.get("/api/market/{symbol}")
    async def market(symbol: str) -> JSONResponse:
        detail = await store.market_series(symbol)
        return JSONResponse(jsonable_encoder(detail or {"error": "no data"}))

    @app.post("/api/chat")
    async def chat(body: ChatIn) -> dict:
        if body.text.strip():
            await store.send_chat(body.text.strip())
        return {"ok": True}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def _open_browser(url: str) -> None:
    """WSL -> Windows browser via cmd.exe; elsewhere the stdlib way."""
    import os
    import platform

    if "microsoft" in platform.release().lower() or "WSL" in platform.release():
        try:
            os.system(f'cmd.exe /c start "" "{url}" >/dev/null 2>&1')
            return
        except Exception:
            pass
    try:
        webbrowser.open(url)
    except Exception:
        pass


def run() -> int:
    """Blocking entry — ``qs run ui``."""
    import asyncio

    import uvicorn

    settings = load_settings()
    cfg = load_config(settings.config_dir)
    setup_logging("ui", settings.log_dir, settings.log_level)
    port = int(cfg.agent("ui").params.get("port", 8388)) if cfg.agents.get("ui") else 8388

    async def amain() -> None:
        bus = make_bus(settings.bus, settings.nats_url)
        await bus.connect()
        store = DashboardStore(bus, settings, cfg)
        await store.start()
        server = uvicorn.Server(
            uvicorn.Config(create_app(store), host="127.0.0.1", port=port, log_level="warning")
        )
        url = f"http://127.0.0.1:{port}"
        print(f"Quant$warm dashboard -> {url}  (Ctrl+C to stop)")
        _open_browser(url)
        try:
            await server.serve()
        finally:
            await store.stop()
            await bus.close()

    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass
    return 0
