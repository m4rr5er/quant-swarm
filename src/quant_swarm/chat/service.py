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

    async def on_start(self) -> None:
        await self.subscribe(subjects.CHAT_IN, self._on_user_msg)
        await self.subscribe(subjects.CHAT_OUT_ALL, self._on_expert_msg)
        logger.info("chat ready (router + session store)")

    async def _on_user_msg(self, msg: BusMessage) -> None:
        env = msg.envelope()
        chat = env.unwrap(ChatMessage)
        await self._persist(chat, env.trace_id)
        route = classify(chat.content)
        self.bump("routed")
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
