"""Dashboard bootstrap — QApplication + qasync loop + DashboardStore."""

from __future__ import annotations

import asyncio
import sys

from quant_swarm.core.bus import make_bus
from quant_swarm.core.config import load_config, load_settings
from quant_swarm.core.logging import setup_logging


def run() -> int:
    """Blocking entry — ``qs run ui`` / ``python -m quant_swarm.ui``."""
    settings = load_settings()
    cfg = load_config(settings.config_dir)
    setup_logging("ui", settings.log_dir, settings.log_level)

    import qasync
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow
    from .store import DashboardStore
    from .theme import FONT_FAMILIES, STYLE

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Quant$warm")
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    app.setFont(font)
    app.setStyleSheet(STYLE)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    async def amain() -> None:
        bus = make_bus(settings.bus, settings.nats_url)
        await bus.connect()
        store = DashboardStore(bus, settings, cfg)
        await store.start()
        win = MainWindow(store)
        win.show()
        await win.refresh_portfolio()
        closed = loop.create_future()
        app.aboutToQuit.connect(lambda: not closed.done() and closed.set_result(None))
        try:
            await closed
        finally:
            await store.stop()
            await bus.close()

    with loop:
        loop.run_until_complete(amain())
    return 0
