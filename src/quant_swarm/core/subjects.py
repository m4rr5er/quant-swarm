"""Bus subject namespace — the only cross-process API surface.

Wildcard semantics follow NATS: ``*`` matches exactly one token,
``>`` matches the remaining tail (only legal at the end).
"""

from __future__ import annotations

PREFIX = "qs"


def ctrl_collect(agent: str) -> str:
    return f"{PREFIX}.ctrl.collect.{agent}"


def ctrl_collect_all() -> str:
    return f"{PREFIX}.ctrl.collect.*"


CTRL_DECIDE = f"{PREFIX}.ctrl.decide"
CTRL_BACKTEST = f"{PREFIX}.ctrl.backtest"


def cards_market(symbol: str) -> str:
    return f"{PREFIX}.cards.market.{symbol}"


CARDS_MARKET_ALL = f"{PREFIX}.cards.market.>"
CARDS_FUNDAMENTAL = f"{PREFIX}.cards.fundamental"
CARDS_CAPITAL = f"{PREFIX}.cards.capital"
CARDS_BACKTEST = f"{PREFIX}.cards.backtest"
ALERTS_EVENTS = f"{PREFIX}.alerts.events"
DECISIONS = f"{PREFIX}.decisions"
ORDERS = f"{PREFIX}.orders"
FILLS = f"{PREFIX}.fills"
RISK_VETO = f"{PREFIX}.risk.veto"


CHAT_IN = f"{PREFIX}.chat.in"


def chat_out(channel: str) -> str:
    return f"{PREFIX}.chat.out.{channel}"


CHAT_OUT_ALL = f"{PREFIX}.chat.out.>"


def expert_task(name: str) -> str:
    return f"{PREFIX}.expert.{name}"


EXPERT_TASK_ALL = f"{PREFIX}.expert.>"


def cosign(group: str, expert: str) -> str:
    """Co-sign opinion channel: qs.cosign.<group>.<expert> — internal only."""
    return f"{PREFIX}.cosign.{group}.{expert}"


COSIGN_ALL = f"{PREFIX}.cosign.>"


def dlq(agent: str) -> str:
    """Dead-letter queue — undeliverable/failed messages per consumer."""
    return f"{PREFIX}.dlq.{agent}"


DLQ_ALL = f"{PREFIX}.dlq.>"


def heartbeat(agent: str) -> str:
    return f"{PREFIX}.heartbeat.{agent}"


HEARTBEAT_ALL = f"{PREFIX}.heartbeat.>"


def match_subject(pattern: str, subject: str) -> bool:
    """Return True if ``subject`` matches ``pattern`` under NATS rules."""
    p, s = pattern.split("."), subject.split(".")
    for i, tok in enumerate(p):
        if tok == ">":
            return i == len(p) - 1
        if i >= len(s) or (tok != "*" and tok != s[i]):
            return False
    return len(p) == len(s)
