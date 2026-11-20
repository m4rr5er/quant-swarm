"""ExpertService — a conversational decision-AI that commands the worker team.

Each expert (``investor`` / ``quant``) is a process driven by a versioned
persona file plus its bounded memory. On ``qs.expert.<name>`` it receives an
ExpertTask, then runs a tool loop: the LLM either calls a tool (dispatch
worker jobs, read cards/portfolio/risk, search sessions, edit memory) or
replies. The loop IS the acceptance step — the persona checklist makes the
model verify freshness/coverage/consistency before it may reply; the
programmatic floor just caps iterations. Answers go to
``qs.chat.out.<channel>`` carrying the task's trace_id.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import desc, select

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage, MessageBus
from quant_swarm.core.config import AppConfig, Settings
from quant_swarm.core.db.models import (
    AccountRow,
    DecisionRow,
    FillRow,
    InfoCardRow,
    MessageRow,
    PositionRow,
)
from quant_swarm.core.llm import LLMClient, LLMConfigError
from quant_swarm.core.memory import expert_memory, user_memory
from quant_swarm.core.paths import persona_path
from quant_swarm.core.schemas import (
    ChatMessage,
    ChatRole,
    CtrlCommand,
    ExpertTask,
    RiskEvent,
)
from quant_swarm.core.timeutils import utcnow

PROMPT_VERSION = "expert_v1"

TOOL_SPEC = """\
你可以调用以下工具指挥工作团队与查询数据。每次只输出一个动作。
- dispatch_collect(agent)                派采集任务。agent ∈ market_data|fundamentals|capital_flow
- trigger_decide()                       让决策引擎(brain)对全部持仓标的跑一轮决策
- read_cards(symbols=[], kinds=[], limit=10)   读最新信息卡。kinds ∈ MARKET | FUNDAMENTAL | CAPITAL
- read_portfolio()                       持仓、现金/权益、最近成交
- read_risk_events(limit=10)             近期风控/异动事件
- run_backtest(symbol, strategy="ma_cross", params={"short":5,"long":20})  派回测任务，返回绩效统计
- session_search(query)                  全文检索历史会话
- memory(action, title, body)            维护你的工作笔记。action ∈ list | set | remove
验收纪律：回答前核对 ①数据是否当日/新鲜 ②覆盖任务要求的标的 ③多来源是否一致。
涉及具体标的/行情/持仓/策略数据的任务，必须先调用工具获取数据再回答；
除非问题是纯概念讨论，否则"取不到数据"不可作为不调用工具的理由。"""


class ExpertAction(BaseModel):
    """LLM output contract — one tool call or the final reply.

    Field/value aliases are normalised before validation: relay models
    routinely write ``answer``/``final``/``arguments``/``text`` instead
    of the literal contract — that drift is not a parse failure.
    """

    model_config = {"populate_by_name": True}

    type: Literal["tool", "reply"]
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    content: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        for canon, aliases in (
            ("tool", ("name", "tool_name", "function", "action")),
            ("args", ("arguments", "params", "parameters")),
            ("content", ("text", "message", "answer", "response")),
        ):
            for a in aliases:
                if canon not in d and a in d:
                    d[canon] = d.pop(a)
        t = str(d.get("type", "")).lower()
        if t in ("answer", "final", "response", "respond", "text", "final_answer"):
            d["type"] = "reply"
        elif t in ("call", "tool_call", "use_tool", "function", "action"):
            d["type"] = "tool"
        if "type" not in d:
            d["type"] = "reply" if d.get("content") else "tool"
        return d


class ExpertService(AgentBase):
    """Conversational expert. ``expert_name`` selects persona & memory."""

    def __init__(
        self,
        bus: MessageBus,
        settings: Settings,
        cfg: AppConfig,
        *,
        expert_name: str,
        client: LLMClient | None = None,
    ) -> None:
        self.name = expert_name
        super().__init__(bus, settings, cfg)
        self.memory = expert_memory(settings.memory_dir, expert_name)
        self.user_memory = user_memory(settings.memory_dir)
        self.persona = persona_path(expert_name).read_text(encoding="utf-8")
        self._client = client if client is not None else self._build_client()
        self._risk_events: list[RiskEvent] = []
        self._tools = {
            "dispatch_collect": self._tool_dispatch_collect,
            "trigger_decide": self._tool_trigger_decide,
            "read_cards": self._tool_read_cards,
            "read_portfolio": self._tool_read_portfolio,
            "read_risk_events": self._tool_risk_events,
            "run_backtest": self._tool_run_backtest,
            "session_search": self._tool_session_search,
            "memory": self._tool_memory,
        }

    def _build_client(self) -> LLMClient | None:
        profile = self.cfg.llm.profiles.get(self.spec.llm_profile or "")
        if profile is None:
            logger.warning("{}: llm profile {!r} missing", self.name, self.spec.llm_profile)
            return None
        try:
            return LLMClient(profile)
        except LLMConfigError as exc:
            logger.warning("{}: {}", self.name, exc)
            return None

    async def on_start(self) -> None:
        await self.subscribe(subjects.expert_task(self.name), self._on_task)
        await self.subscribe(subjects.ALERTS_EVENTS, self._on_alert)
        logger.info(
            "{} ready (persona {} chars, llm={})",
            self.name,
            len(self.persona),
            self._client.profile.model if self._client else "OFFLINE",
        )

    async def _on_alert(self, msg: BusMessage) -> None:
        self._risk_events.append(msg.envelope().unwrap(RiskEvent))
        self._risk_events = self._risk_events[-200:]

    async def _on_task(self, msg: BusMessage) -> None:
        env = msg.envelope()
        task = env.unwrap(ExpertTask)
        bound = logger.bind(trace_id=env.trace_id, expert=self.name)
        self.bump("tasks")
        if self._client is None:
            await self._reply(
                task,
                env.trace_id,
                "（离线）未配置 LLM 档案，暂无法处理任务。"
                "请在 agents.yaml 为本专家配置 llm_profile 并注入密钥。",
            )
            return
        try:
            answer, refs = await self._run_loop(task, bound)
        except Exception as exc:
            self.bump("errors")
            bound.exception("expert loop failed")
            answer, refs = f"（处理失败：{type(exc).__name__}）请稍后重试。", []
        await self._reply(task, env.trace_id, answer, refs)

    # -- the tool/acceptance loop ---------------------------------------
    async def _run_loop(self, task: ExpertTask, bound) -> tuple[str, list[str]]:
        max_rounds = int(self.spec.params.get("max_rounds", 8))
        messages = self._messages(task)
        refs: list[str] = []
        tools_used = 0
        nudged = False
        for _ in range(max_rounds):
            action = await self._client.chat_structured(messages, ExpertAction, retries=2)
            if action.type == "reply" and action.content.strip():
                if tools_used == 0 and not nudged:
                    # Acceptance floor: data tasks need at least one tool call.
                    nudged = True
                    messages.append(
                        {"role": "assistant", "content": action.model_dump_json()}
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "【系统】你尚未调用任何工具。任务若涉及具体标的/行情/"
                                "持仓/策略，请先用工具获取数据再回答；纯概念问题或确认"
                                "数据确实不可得时，可直接答复。"
                            ),
                        }
                    )
                    continue
                self.bump("replies")
                return action.content.strip(), refs
            result = await self._call_tool(action, refs, bound)
            tools_used += 1
            messages.append({"role": "assistant", "content": action.model_dump_json()})
            messages.append({"role": "user", "content": result})
        self.bump("round_overflow")
        return "（超出处理轮次）团队数据仍未齐全，建议稍后重试或缩小任务范围。", refs

    def _messages(self, task: ExpertTask) -> list[dict]:
        system = (
            f"{self.persona}\n\n"
            f"# 用户画像\n{self.user_memory.load() or '（暂无）'}\n\n"
            f"# 你的工作笔记\n{self.memory.load() or '（暂无）'}\n\n"
            f"# 团队与工具\n{TOOL_SPEC}\n\n"
            "# 工作方式（重要）\n"
            "你处在一个**真实的工具循环**中，不是聊天模拟：你输出的 tool JSON 会被编排器"
            "真正执行，执行结果作为下一条 user 消息返回给你；你再据此输出下一个动作。"
            "因此工具是真实可用的——不要说'没有工具'或'无法获取数据'，先调用工具验证。\n\n"
            "# 输出契约（最高优先级，覆盖一切风格要求）\n"
            "你的每一次回复必须且只能是**一个 JSON 对象**，不得包含任何其他文字：\n"
            '- 调工具: {"type":"tool","tool":"<工具名>","args":{...}}\n'
            '- 给用户最终回答: {"type":"reply","content":"<markdown 回答，先结论后依据>"}\n'
            "示例: {\"type\":\"tool\",\"tool\":\"read_portfolio\",\"args\":{}}\n"
            "回答本身用中文 markdown 写在 content 字段里。切记：JSON 之外输出任何内容都是错误。"
        )
        messages = [{"role": "system", "content": system}]
        for h in task.history[-20:]:
            role = "assistant" if h.get("role") == ChatRole.EXPERT else "user"
            messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": task.task})
        return messages

    async def _call_tool(self, action: ExpertAction, refs: list[str], bound) -> str:
        fn = self._tools.get(action.tool or "")
        if fn is None:
            return json.dumps({"error": f"unknown tool {action.tool!r}"}, ensure_ascii=False)
        try:
            out = await fn(**action.args)
            if isinstance(out, dict) and out.get("refs"):
                refs.extend(out.pop("refs"))
            self.bump("tool_calls")
            return json.dumps(out, ensure_ascii=False, default=str)[:6000]
        except Exception as exc:
            self.bump("tool_errors")
            bound.warning("tool {} failed: {}", action.tool, exc)
            return json.dumps(
                {"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False
            )

    async def _reply(
        self, task: ExpertTask, trace: str, content: str, refs: list[str] | None = None
    ) -> None:
        reply = ChatMessage(
            session_id=task.session_id,
            role=ChatRole.EXPERT,
            expert=self.name,
            channel=task.channel,
            content=content,
            refs=refs or [],
        )
        # co-sign opinions go to the internal cosign channel; normal
        # answers go to the user-facing out channel.
        subject = task.context.get("reply_subject") or subjects.chat_out(task.channel)
        await self.bus.publish_model(subject, reply, trace_id=trace)

    # -- tools -----------------------------------------------------------
    async def _tool_dispatch_collect(self, agent: str) -> dict:
        if agent not in ("market_data", "fundamentals", "capital_flow"):
            return {"error": f"no such worker {agent!r}"}
        t0 = utcnow()
        await self.bus.publish_model(
            subjects.ctrl_collect(agent), CtrlCommand(command="collect", args={"by": self.name})
        )
        wait = float(self.spec.params.get("collect_wait_sec", 25))
        rows = await self._wait_cards(agent, t0, wait)
        return {
            "dispatched": agent,
            "new_cards": len(rows),
            "cards": rows,
            "refs": [r["card_id"] for r in rows],
        }

    async def _wait_cards(
        self, agent: str, t0, wait_sec: float, include_payload: bool = False
    ) -> list[dict]:
        deadline = wait_sec
        while True:
            async with self.sessions() as s:
                rows = (
                    (
                        await s.execute(
                            select(InfoCardRow)
                            .where(InfoCardRow.agent == agent, InfoCardRow.received_ts > t0)
                            .order_by(desc(InfoCardRow.received_ts))
                        )
                    )
                    .scalars()
                    .all()
                )
            if rows or deadline <= 0:
                return [
                    {
                        "card_id": r.card_id,
                        "kind": r.kind,
                        "symbols": r.symbols,
                        "asof": r.asof.isoformat(),
                        "confidence": r.confidence,
                        **({"payload": r.payload} if include_payload else {}),
                    }
                    for r in rows
                ]
            await asyncio.sleep(0.5)
            deadline -= 0.5

    async def _tool_trigger_decide(self) -> dict:
        t0 = utcnow()
        await self.bus.publish_model(
            subjects.CTRL_DECIDE, CtrlCommand(command="decide", args={"by": self.name})
        )
        deadline = float(self.spec.params.get("collect_wait_sec", 25))
        while True:
            async with self.sessions() as s:
                rows = (
                    (
                        await s.execute(
                            select(DecisionRow).where(DecisionRow.ts > t0)
                        )
                    )
                    .scalars()
                    .all()
                )
            if rows or deadline <= 0:
                return {
                    "decisions": [
                        {
                            "symbol": r.symbol,
                            "action": r.action,
                            "target_weight": r.target_weight,
                            "qty": r.qty,
                            "rationale": r.rationale[:300],
                        }
                        for r in rows
                    ],
                    "refs": [r.decision_id for r in rows],
                }
            await asyncio.sleep(0.5)
            deadline -= 0.5

    async def _tool_read_cards(
        self, symbols: list[str] | None = None, kinds: list[str] | None = None, limit: int = 10
    ) -> dict:
        q = select(InfoCardRow).order_by(desc(InfoCardRow.received_ts)).limit(min(limit, 50))
        if kinds:
            q = q.where(InfoCardRow.kind.in_([k.upper() for k in kinds]))
        async with self.sessions() as s:
            rows = (await s.execute(q)).scalars().all()
        if symbols:
            wanted = set(symbols)
            rows = [r for r in rows if wanted & set(r.symbols or [])]
        cards = [
            {
                "card_id": r.card_id,
                "kind": r.kind,
                "agent": r.agent,
                "symbols": r.symbols,
                "asof": r.asof.isoformat(),
                "confidence": r.confidence,
                "payload": r.payload,
            }
            for r in rows
        ]
        return {"cards": cards, "refs": [r.card_id for r in rows]}

    async def _tool_read_portfolio(self) -> dict:
        async with self.sessions() as s:
            positions = (await s.execute(select(PositionRow))).scalars().all()
            account = (
                await s.execute(select(AccountRow).where(AccountRow.account_id == "paper"))
            ).scalar_one_or_none()
            fills = (
                (await s.execute(select(FillRow).order_by(desc(FillRow.ts)).limit(10)))
                .scalars()
                .all()
            )
        return {
            "account": (
                {"cash": account.cash, "equity": account.equity} if account else None
            ),
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": p.qty,
                    "avg_cost": p.avg_cost,
                    "realized_pnl": p.realized_pnl,
                }
                for p in positions
            ],
            "recent_fills": [
                {
                    "order_id": f.order_id,
                    "status": f.status,
                    "qty": f.filled_qty,
                    "price": f.avg_price,
                    "ts": f.ts.isoformat(),
                }
                for f in fills
            ],
        }

    async def _tool_risk_events(self, limit: int = 10) -> dict:
        cutoff = utcnow() - timedelta(hours=48)
        events = [
            {
                "level": str(e.level),
                "code": e.code,
                "message": e.message,
                "symbols": e.symbols,
                "veto": e.veto,
                "ts": e.ts.isoformat(),
            }
            for e in self._risk_events
            if e.ts >= cutoff
        ]
        return {"risk_events": events[-limit:]}

    async def _tool_run_backtest(
        self, symbol: str, strategy: str = "ma_cross", params: dict | None = None
    ) -> dict:
        t0 = utcnow()
        await self.bus.publish_model(
            subjects.CTRL_BACKTEST,
            CtrlCommand(
                command="backtest",
                args={"symbol": symbol, "strategy": strategy, "params": params or {}},
            ),
        )
        wait = float(self.spec.params.get("collect_wait_sec", 25))
        rows = await self._wait_cards("backtester", t0, wait, include_payload=True)
        if not rows:
            return {"error": f"backtester returned nothing for {symbol} within {wait}s"}
        return {"backtests": rows, "refs": [r["card_id"] for r in rows]}

    async def _tool_session_search(self, query: str) -> dict:
        """Substring search over session history — CJK-safe (FTS5's default
        tokenizer can't segment Chinese, so we LIKE the messages table)."""
        like = f"%{query.strip()}%"
        async with self.sessions() as s:
            rows = (
                (
                    await s.execute(
                        select(MessageRow)
                        .where(MessageRow.content.like(like))
                        .order_by(desc(MessageRow.ts))
                        .limit(8)
                    )
                )
                .scalars()
                .all()
            )
        return {
            "hits": [
                {
                    "session_id": r.session_id,
                    "expert": r.expert or r.role,
                    "snippet": r.content[:120],
                    "ts": r.ts.isoformat(),
                }
                for r in rows
            ]
        }

    async def _tool_memory(self, action: str, title: str = "", body: str = "") -> dict:
        if action == "list":
            return {"sections": list(self.memory.sections())}
        if action == "set":
            self.memory.set(title, body)
            return {"ok": True, "section": title}
        if action == "remove":
            return {"ok": self.memory.remove(title)}
        return {"error": f"unknown memory action {action!r}"}
