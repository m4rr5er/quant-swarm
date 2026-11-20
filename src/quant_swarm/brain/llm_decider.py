"""LLM decision path — structured Decision via a named profile.

The model only proposes (action, target_weight, rationale); hard numbers
(qty, clamping, veto) are enforced afterwards by the guardrails + sizer in
``service.py`` so an over-eager model can't break the risk limits.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from quant_swarm.core.llm import LLMClient
from quant_swarm.core.schemas import Action, InfoCard, RiskEvent

PROMPT_VERSION = "decision_v1"

_SYSTEM = """You are the decision brain of a cautious A-share paper-trading system.
You receive fact cards (market data with indicators, fundamentals, capital
flow) and recent risk events for ONE symbol, plus the current paper position.

Reply with ONE JSON object:
{"action": "BUY|ADD|REDUCE|SELL|HOLD", "target_weight": <float 0..1 or null>,
 "rationale": "<one or two sentences, cite the cards that drove the call>",
 "confidence": <float 0..1>}

Rules:
- target_weight = the fraction of TOTAL equity this position should occupy
  after the trade. null/0 with SELL means exit fully.
- Never exceed max_weight. When in doubt, HOLD.
- BUY/ADD only when you intend to increase exposure; REDUCE/SELL to cut it.
- A CRITICAL risk event on the symbol means HOLD or reduce — never add.
- Keep rationale short and factual; mention numbers."""


class LLMDecisionOut(BaseModel):
    action: Action
    target_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


def _card_digest(card: InfoCard) -> dict[str, Any]:
    """Compact card view for the prompt — indicators + small slices only."""
    kind, payload = str(card.kind), card.payload
    if kind == "market":
        closes = payload.get("closes") or []
        return {
            "kind": kind,
            "card_id": card.card_id,
            "asof": card.asof.isoformat(),
            "last_close": closes[-1] if closes else None,
            "closes_tail": closes[-10:],
            "indicators": payload.get("indicators"),
        }
    return {
        "kind": kind,
        "card_id": card.card_id,
        "asof": card.asof.isoformat(),
        "payload": payload,
    }


def build_messages(
    *,
    symbol: str,
    market_card: InfoCard,
    extra_cards: list[InfoCard],
    position_qty: int,
    equity: float,
    max_weight: float,
    risk_events: list[RiskEvent],
) -> list[dict[str, Any]]:
    import json

    context = {
        "symbol": symbol,
        "max_weight": max_weight,
        "equity": equity,
        "position_qty": position_qty,
        "cards": [_card_digest(market_card), *(_card_digest(c) for c in extra_cards)],
        "risk_events": [
            {
                "code": e.code,
                "level": str(e.level),
                "message": e.message,
                "veto": e.veto,
                "ts": e.ts.isoformat(),
            }
            for e in risk_events
        ],
    }
    return [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Decide for {symbol}.\n"
                f"{json.dumps(context, ensure_ascii=False, default=str)}"
            ),
        },
    ]


class LLMDecider:
    """One LLM call per symbol -> :class:`LLMDecisionOut`."""

    def __init__(self, client: LLMClient, *, prompt_version: str = PROMPT_VERSION) -> None:
        self.client = client
        self.prompt_version = prompt_version

    async def decide(
        self,
        *,
        symbol: str,
        market_card: InfoCard,
        extra_cards: list[InfoCard],
        position_qty: int,
        equity: float,
        max_weight: float,
        risk_events: list[RiskEvent],
    ) -> LLMDecisionOut:
        messages = build_messages(
            symbol=symbol,
            market_card=market_card,
            extra_cards=extra_cards,
            position_qty=position_qty,
            equity=equity,
            max_weight=max_weight,
            risk_events=risk_events,
        )
        return await self.client.chat_structured(messages, LLMDecisionOut)
