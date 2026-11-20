"""Event monitor agent (Agent 4) — reactive spike detector.

Subscribes to market InfoCards and emits ``RiskEvent`` on
``qs.alerts.events`` when |day change| crosses thresholds. No polling —
it reacts to whatever market_data publishes.
"""

from __future__ import annotations

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, MessageBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.schemas import InfoCard, RiskEvent, RiskLevel


def day_change(card: InfoCard) -> float | None:
    """Last-close pct change from a market card's ``closes`` payload."""
    closes = card.payload.get("closes") or []
    if len(closes) < 2 or not closes[-2]:
        return None
    return closes[-1] / closes[-2] - 1


class EventMonitorAgent(AgentBase):
    name = "event_monitor"

    def __init__(self, bus: MessageBus, settings: Settings, cfg: AppConfig) -> None:
        super().__init__(bus, settings, cfg)
        self._warn = float(self.spec.params.get("spike_pct", 0.05))
        self._crit = float(self.spec.params.get("critical_pct", 0.09))

    async def on_start(self) -> None:
        await self.subscribe(subjects.CARDS_MARKET_ALL, self._on_market_card)
        self.bound.info(
            "subscribed {} (warn={} crit={})",
            subjects.CARDS_MARKET_ALL,
            self._warn,
            self._crit,
        )

    async def _on_market_card(self, msg: BusMessage) -> None:
        trace = msg.envelope().trace_id
        card = msg.envelope().unwrap(InfoCard)
        symbol = card.symbols[0] if card.symbols else "?"
        chg = day_change(card)
        if chg is None:
            self.bump("skipped")
            return
        level: RiskLevel | None = None
        if abs(chg) >= self._crit:
            level = RiskLevel.CRITICAL
        elif abs(chg) >= self._warn:
            level = RiskLevel.WARN
        if level is None:
            self.bump("quiet")
            return
        direction = "UP" if chg > 0 else "DOWN"
        event = RiskEvent(
            code=f"PRICE_SPIKE_{direction}",
            level=level,
            symbols=[symbol],
            message=(
                f"day change {chg:+.2%} "
                f"(warn {self._warn:.0%} / crit {self._crit:.0%})"
            ),
            veto=level == RiskLevel.CRITICAL and direction == "DOWN",
            source=self.name,
        )
        await self.bus.publish_model(subjects.ALERTS_EVENTS, event, trace_id=trace)
        self.bump("alerts")
        self.bound.warning("spike {} {:+.2%} → {}", symbol, chg, level)
