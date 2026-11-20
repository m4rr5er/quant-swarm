"""ChatService — router + session store between user and experts.

In : user ChatMessage on qs.chat.in -> persist -> classify -> ExpertTask
on qs.expert.<name> carrying recent session history.
Out: expert ChatMessage on qs.chat.out.* -> persist (+FTS index) so
channels (dashboard/IM) stay dumb renderers.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy import select, text, update

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage
from quant_swarm.core.db.models import MessageRow, SessionRow
from quant_swarm.core.ids import new_id
from quant_swarm.core.schemas import ChatMessage, ExpertTask
from quant_swarm.core.timeutils import utcnow

from .router import classify

HISTORY_FOR_TASK = 20

_FTS_INSERT = text(
    "INSERT INTO messages_fts(rowid, content, session_id, expert) "
    "VALUES (:id, :content, :session_id, :expert)"
)


class ChatService(AgentBase):
    name = "chat"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # cosign group -> {primary, session, channel, task, opinions, trace}
        self._cosign: dict[str, dict] = {}

    async def on_start(self) -> None:
        await self.subscribe(subjects.CHAT_IN, self._on_user_msg)
        await self.subscribe(subjects.CHAT_OUT_ALL, self._on_expert_msg)
        await self.subscribe(subjects.COSIGN_ALL, self._on_cosign)
        logger.info("chat ready (router + session store + co-signing)")

    async def _on_user_msg(self, msg: BusMessage) -> None:
        env = msg.envelope()
        chat = env.unwrap(ChatMessage)
        await self._persist(chat, env.trace_id)
        route = classify(chat.content)
        self.bump("routed")
        if route.compound:
            await self._dispatch_cosign(chat, env.trace_id, route)
            return
        history = await self._history(chat.session_id)
        task = ExpertTask(
            session_id=chat.session_id,
            channel=chat.channel,
            task=chat.content,
            history=history,
            context={
                "route": {
                    "expert": route.expert,
                    "compound": route.compound,
                    "score_investor": route.score_investor,
                    "score_quant": route.score_quant,
                }
            },
        )
        await self.bus.publish_model(
            subjects.expert_task(route.expert), task, trace_id=env.trace_id
        )
        logger.info(
            "routed -> {} (compound={} i{} q{})",
            route.expert,
            route.compound,
            route.score_investor,
            route.score_quant,
        )

    # -- co-signing ------------------------------------------------------
    async def _dispatch_cosign(self, chat: ChatMessage, trace: str, route) -> None:
        """Compound task -> both experts independently, then synthesize."""
        group = new_id("cg")
        history = await self._history(chat.session_id)
        self._cosign[group] = {
            "primary": route.expert,
            "session": chat.session_id,
            "channel": chat.channel,
            "task": chat.content,
            "history": history,
            "opinions": {},
            "trace": trace,
        }
        for name in ("investor", "quant"):
            task = ExpertTask(
                session_id=chat.session_id,
                channel=chat.channel,
                task=chat.content,
                history=history,
                context={
                    "cosign_group": group,
                    "cosign_role": "opinion",
                    "primary": route.expert,
                    "reply_subject": subjects.cosign(group, name),
                },
            )
            await self.bus.publish_model(subjects.expert_task(name), task, trace_id=trace)
        logger.info("cosign {} -> investor+quant (primary={})", group, route.expert)
        self.bump("cosign")

    async def _on_cosign(self, msg: BusMessage) -> None:
        """Collect cosign opinions; when both experts have spoken, synthesize."""
        env = msg.envelope()
        try:
            chat = env.unwrap(ChatMessage)
        except Exception:
            return
        # qs.cosign.<group>.<expert>
        parts = msg.subject.split(".")
        if len(parts) < 4 or parts[2] not in self._cosign:
            return
        group = self._cosign[parts[2]]
        expert = parts[3]
        group["opinions"][expert] = chat.content
        await self._persist(chat, env.trace_id)  # keep opinions in history
        self.bump("cosign_opinions")
        if len(group["opinions"]) >= 2:
            await self._synthesize(parts[2], group)

    async def _synthesize(self, group_id: str, group: dict) -> None:
        """Primary expert merges both opinions into the single final answer."""
        del self._cosign[group_id]
        opinions = "\n\n".join(
            f"【{name} 专家意见】\n{txt}" for name, txt in group["opinions"].items()
        )
        task = ExpertTask(
            session_id=group["session"],
            channel=group["channel"],
            task=(
                f"这是会签任务。用户问题：『{group['task']}』\n\n"
                f"{opinions}\n\n"
                "请合成一份给用户的最终回答（中文 markdown）：保留双方共识，"
                "分歧点显式标注，先给结论再给依据。"
            ),
            history=group["history"],
            context={"cosign_role": "synthesis"},
        )
        await self.bus.publish_model(
            subjects.expert_task(group["primary"]), task, trace_id=group["trace"]
        )
        logger.info("cosign {} synthesized by {}", group_id, group["primary"])
        self.bump("cosign_synthesized")

    async def _on_expert_msg(self, msg: BusMessage) -> None:
        env = msg.envelope()
        try:
            chat = env.unwrap(ChatMessage)
        except Exception:
            logger.warning("non-chat payload on {}", msg.subject)
            return
        await self._persist(chat, env.trace_id)
        self.bump("replies")

    # -- persistence -----------------------------------------------------
    async def _persist(self, chat: ChatMessage, trace: str) -> None:
        async with self.sessions() as s:
            sess = (
                await s.execute(
                    select(SessionRow).where(SessionRow.session_id == chat.session_id)
                )
            ).scalar_one_or_none()
            if sess is None:
                sess = SessionRow(
                    session_id=chat.session_id,
                    channel=str(chat.channel),
                    started_ts=utcnow(),
                    last_ts=utcnow(),
                )
                s.add(sess)
            else:
                await s.execute(
                    update(SessionRow)
                    .where(SessionRow.session_id == chat.session_id)
                    .values(last_ts=utcnow())
                )
            row = MessageRow(
                session_id=chat.session_id,
                role=str(chat.role),
                expert=chat.expert,
                channel=str(chat.channel),
                content=chat.content,
                refs=chat.refs,
                trace_id=trace,
                ts=chat.ts if isinstance(chat.ts, datetime) else utcnow(),
            )
            s.add(row)
            await s.flush()
            try:
                await s.execute(
                    _FTS_INSERT,
                    {
                        "id": row.id,
                        "content": chat.content,
                        "session_id": chat.session_id,
                        "expert": chat.expert or "",
                    },
                )
            except Exception:
                logger.debug("fts insert skipped (table missing?)")
            await s.commit()

    async def _history(self, session_id: str) -> list[dict]:
        async with self.sessions() as s:
            rows = (
                (
                    await s.execute(
                        select(MessageRow)
                        .where(MessageRow.session_id == session_id)
                        .order_by(MessageRow.ts.desc())
                        .limit(HISTORY_FOR_TASK)
                    )
                )
                .scalars()
                .all()
            )
        rows.reverse()
        return [
            {"role": r.role, "expert": r.expert, "content": r.content, "ts": r.ts.isoformat()}
            for r in rows
        ]
