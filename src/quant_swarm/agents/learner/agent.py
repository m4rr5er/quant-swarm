"""Learner — the M5c self-improvement loop.

One cycle:
1. observe — bounded scan of the operational store (recent chat turns,
   dead letters, failed job runs, activity counts) plus current memory
   files;
2. reflect — one structured LLM call returning memory ops + an optional
   skill proposal;
3. apply — ops go through the bounded ``MemoryFile`` surface (overflow
   triggers one consolidate-and-retry);
4. report — ``ReviewReport`` on ``qs.learn.report`` + ``review_reports``
   row so the dashboard learning tab has something to read.

Workers are plain processes — they can't reflect on themselves — so the
learner writes ``agents/*.md`` *for* them and arbitrates ``USER.md``
(two experts editing one file would rot it). Runs on a timer and on
``qs.ctrl.learn``; without an LLM key it idles quietly.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage
from quant_swarm.core.db.models import (
    DLQRow,
    InfoCardRow,
    JobRunRow,
    MessageRow,
    ReviewReportRow,
)
from quant_swarm.core.llm import LLMClient, LLMConfigError
from quant_swarm.core.memory import MemoryFile, agent_memory, expert_memory, user_memory
from quant_swarm.core.paths import skill_dir
from quant_swarm.core.schemas import ReviewReport
from quant_swarm.core.timeutils import utcnow

PROMPT_VERSION = "learner_v1"


class MemoryOp(BaseModel):
    target: str  # "USER.md" | "agents/<name>.md" | "experts/<name>.md"
    title: str
    body: str


class LearnOutput(BaseModel):
    summary: str = ""
    ops: list[MemoryOp] = Field(default_factory=list)
    skill_proposal: dict[str, str] | None = None  # {agent, content}


_SYSTEM = """你是 Quant$warm 的"学习器"。你的任务是让整个系统越用越顺手。

你看到的输入：
- 最近的对话流水（用户 ↔ 决策专家）
- 系统运行痕迹：死信、失败 job、各组件产出计数
- 当前的记忆文件：USER.md（用户画像）、agents/*.md（worker 经验）、experts/*.md（专家笔记）

你要输出的 JSON：
{
  "summary": "一句话：本轮学到什么/为什么没学到",
  "ops": [{"target": "USER.md|agents/<名>.md|experts/<名>.md",
           "title": "小节标题", "body": "内容"}],
  "skill_proposal": {"agent": "<组件名>", "content": "<完整技能 markdown>"} | null
}

纪律：
- 只写有证据支撑的内容；没有新信息时 ops 为空、summary 说明原因。
- USER.md：用户偏好/习惯/反馈风格——只有用户明确表现过才写。
- agents/*.md：worker 的操作性知识（数据坑、报错模式、有效参数）——依据死信/job 失败写。
- experts/*.md：专家自我改进的线索（重复回答模式、被追问的薄弱点）。
- 每个文件有字符上限——写新增/更新，不要重复已有小节；同标题即覆盖。
- skill_proposal 只在发现可复用的稳定模式时才给（例如某类任务反复用的分析流程）。
- 输出必须是纯 JSON，不要任何额外文字。"""


class LearnerService(AgentBase):
    name = "learner"

    def __init__(self, bus, settings, cfg, *, client: Any | None = None) -> None:
        super().__init__(bus, settings, cfg)
        self._client = client
        self._loop_task: asyncio.Task | None = None

    async def on_start(self) -> None:
        if self._client is None:
            profile = self.cfg.llm.profiles.get(self.spec.llm_profile or "")
            try:
                self._client = LLMClient(profile) if profile else None
            except LLMConfigError:
                self._client = None
        await self.subscribe(subjects.CTRL_LEARN, self._on_ctrl)
        interval = float(self.spec.params.get("interval_min", 60))
        if interval > 0:
            self._loop_task = asyncio.create_task(self._timer(interval))
        state = self._client.profile.model if self._client else "OFFLINE"
        logger.info("learner ready (interval={}min, llm={})", interval, state)

    async def on_stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()

    async def _timer(self, interval_min: float) -> None:
        while True:
            await asyncio.sleep(interval_min * 60)
            await self.learn_once(trigger="timer")

    async def _on_ctrl(self, msg: BusMessage) -> None:
        await self.learn_once(trigger="ctrl", trace=msg.envelope().trace_id)

    # -- one cycle ---------------------------------------------------------
    async def learn_once(self, *, trigger: str = "manual", trace: str = "") -> ReviewReport:
        if self._client is None:
            return await self._report(
                "observation", "learner offline — no llm key", {"trigger": trigger}, trace
            )
        obs = await self._observe()
        files = self._load_memory_files()
        out = await self._reflect(obs, files)
        applied = [op.model_dump() for op in out.ops if await self._apply_op(op)]
        proposal_path = self._write_proposal(out.skill_proposal)
        self.bump("cycles")
        return await self._report(
            "memory_update",
            out.summary or f"applied {len(applied)} ops",
            {
                "trigger": trigger,
                "ops_applied": applied,
                "skill_proposal": proposal_path,
                "usage": self._client.last_usage,
                "prompt_version": PROMPT_VERSION,
            },
            trace,
        )

    async def _observe(self) -> dict:
        async with self.sessions() as s:
            msgs = (
                (
                    await s.execute(
                        select(MessageRow).order_by(MessageRow.ts.desc()).limit(30)
                    )
                )
                .scalars()
                .all()
            )
            dls = (
                (
                    await s.execute(
                        select(DLQRow).order_by(DLQRow.id.desc()).limit(10)
                    )
                )
                .scalars()
                .all()
            )
            fails = (
                (
                    await s.execute(
                        select(JobRunRow)
                        .where(JobRunRow.status == "failed")
                        .order_by(JobRunRow.started_ts.desc())
                        .limit(10)
                    )
                )
                .scalars()
                .all()
            )
            card_count = (
                await s.execute(select(func.count(InfoCardRow.card_id)))
            ).scalar_one()
            ddl = (
                await s.execute(select(func.count(DLQRow.id)))
            ).scalar_one()
        return {
            "recent_messages": [
                {
                    "role": m.role,
                    "expert": m.expert,
                    "content": m.content[:300],
                    "ts": m.ts.isoformat(),
                }
                for m in reversed(msgs)
            ],
            "dead_letters": [
                {"agent": d.agent, "subject": d.subject, "error": (d.error or "")[:200]}
                for d in dls
            ],
            "dead_letter_total": ddl,
            "failed_jobs": [
                {"job": j.job_name, "error": (j.error or "")[:200]} for j in fails
            ],
            "cards_total": card_count,
        }

    def _load_memory_files(self) -> dict[str, str]:
        files = {"USER.md": user_memory(self.settings.memory_dir).load()}
        agents_dir = self._memory_path("agents")
        if agents_dir.exists():
            for p in sorted(agents_dir.glob("*.md")):
                files[f"agents/{p.name}"] = p.read_text(encoding="utf-8")
        experts_dir = self._memory_path("experts")
        if experts_dir.exists():
            for p in sorted(experts_dir.glob("*.md")):
                files[f"experts/{p.name}"] = p.read_text(encoding="utf-8")
        return files

    def _memory_path(self, sub: str):
        from pathlib import Path

        return Path(self.settings.memory_dir) / sub

    async def _reflect(self, obs: dict, files: dict) -> LearnOutput:
        file_blocks = "\n\n".join(
            f"### {name}\n```\n{content or '(空)'}\n```" for name, content in files.items()
        )
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "## 运行观察\n```json\n"
                    f"{json.dumps(obs, ensure_ascii=False, default=str)[:8000]}"
                    f"\n```\n\n## 当前记忆文件\n{file_blocks[:6000]}"
                ),
            },
        ]
        return await self._client.chat_structured(messages, LearnOutput, retries=2)

    async def _apply_op(self, op: MemoryOp, *, _retry: bool = True) -> bool:
        mf = self._target_file(op.target)
        if mf is None:
            logger.warning("learner: bad memory target {}", op.target)
            return False
        try:
            mf.set(op.title, op.body)
            return True
        except Exception as exc:  # MemoryFullError -> consolidate once
            if not _retry:
                logger.warning("learner: op dropped after retry: {}", exc)
                return False
            compact = await self._consolidate(mf, op)
            return compact

    async def _consolidate(self, mf: MemoryFile, op: MemoryOp) -> bool:
        """File is full — ask the model to merge the new note into a
        tighter version of the whole file, then rewrite via sections."""
        current = mf.load()
        messages = [
            {
                "role": "system",
                "content": "把记忆文件压缩重写：保留全部关键信息，融入新增条目，"
                "输出纯 JSON {\"sections\": {\"标题\": \"内容\"}}，总长尽量短。",
            },
            {
                "role": "user",
                "content": f"当前文件：\n```\n{current}\n```\n新增条目：## {op.title}\n{op.body}",
            },
        ]

        class Sections(BaseModel):
            sections: dict[str, str] = Field(default_factory=dict)

        try:
            out = await self._client.chat_structured(messages, Sections, retries=1)
            for title, body in out.sections.items():
                mf.set(title, body)
            mf.set(op.title, op.body)
            return True
        except Exception as exc:
            logger.warning("learner: consolidate failed: {}", exc)
            return False

    def _target_file(self, target: str) -> MemoryFile | None:
        if target == "USER.md":
            return user_memory(self.settings.memory_dir)
        for prefix, factory in (("agents/", agent_memory), ("experts/", expert_memory)):
            if target.startswith(prefix):
                name = target[len(prefix) :].removesuffix(".md")
                if name and "/" not in name:
                    return factory(self.settings.memory_dir, name)
                return None
        return None

    def _write_proposal(self, proposal: dict[str, str] | None) -> str | None:
        if not proposal or not proposal.get("agent") or not proposal.get("content"):
            return None
        agent = proposal["agent"]
        if "/" in agent or ".." in agent:
            return None
        path = skill_dir(agent) / "proposed.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(proposal["content"].strip() + "\n", encoding="utf-8")
        return str(path)

    async def _report(
        self, kind: str, summary: str, details: dict, trace: str
    ) -> ReviewReport:
        report = ReviewReport(agent="", kind=kind, summary=summary, details=details)
        await self.bus.publish_model(subjects.LEARN_REPORT, report, trace_id=trace)
        async with self.sessions() as s:
            s.add(
                ReviewReportRow(
                    report_id=report.report_id,
                    kind=kind,
                    summary=summary,
                    details=details,
                    trace_id=trace,
                    ts=utcnow(),
                )
            )
            await s.commit()
        logger.info("learner report: {}", summary[:120])
        return report


def main() -> None:
    from quant_swarm.core.runtime import launch

    launch(lambda b, s, c: LearnerService(b, s, c), "learner")


if __name__ == "__main__":
    main()
