"""Unified scheduler — APScheduler triggers -> ctrl messages on the bus.

Each job wraps its publish in a JobRunRow (started/finished/status/error)
so the ops trail lands in sqlite. Interval settings override the crons for
dev/demo runs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.db.models import JobRunRow
from quant_swarm.core.ids import new_id
from quant_swarm.core.schemas import CtrlCommand
from quant_swarm.core.timeutils import utcnow


class SchedulerService(AgentBase):
    name = "scheduler"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._sched: AsyncIOScheduler | None = None

    # Agents driven by qs.ctrl.collect.<name>. event_monitor is reactive
    # (it listens to market cards) so it needs no collect job.
    COLLECT_AGENTS = ("market_data", "fundamentals", "capital_flow")

    async def on_start(self) -> None:
        sched = AsyncIOScheduler()
        s = self.cfg.schedule

        for agent in self.COLLECT_AGENTS:
            spec = self.cfg.agent(agent)
            if not spec.enabled:
                continue
            sched.add_job(
                lambda a=agent: self._job_collect(a),
                self._trigger(
                    str(spec.params.get("cron", s.market_collect_cron)),
                    spec.params.get("interval_sec", s.market_collect_interval_sec),
                ),
                id=f"collect.{agent}",
                name=f"collect {agent}",
                coalesce=True,
            )
        if self.cfg.agent("brain").enabled:
            sched.add_job(
                self._job_decide,
                self._trigger(s.decide_cron, s.decide_interval_sec),
                id="brain.decide",
                name="brain decide",
                coalesce=True,
            )

        sched.start()
        self._sched = sched
        logger.info(
            "scheduler up: jobs={}",
            [j.id for j in sched.get_jobs()],
        )

    async def on_stop(self) -> None:
        if self._sched is not None:
            self._sched.shutdown(wait=False)
            self._sched = None

    @staticmethod
    def _trigger(cron: str, interval_sec: int | None):
        if interval_sec:
            return IntervalTrigger(seconds=interval_sec)
        return CronTrigger.from_crontab(cron)

    async def _job_collect(self, agent: str) -> None:
        await self._run_job(
            f"collect.{agent}",
            lambda trace: self.bus.publish_model(
                subjects.ctrl_collect(agent),
                CtrlCommand(command="collect"),
                trace_id=trace,
            ),
        )

    async def _job_decide(self) -> None:
        await self._run_job(
            "brain.decide",
            lambda trace: self.bus.publish_model(
                subjects.CTRL_DECIDE,
                CtrlCommand(command="decide"),
                trace_id=trace,
            ),
        )

    async def _run_job(self, name: str, work: Callable[[str], Awaitable[object]]) -> None:
        trace = new_id("trace")
        started = utcnow()
        status, error = "OK", None
        try:
            await work(trace)
        except Exception as e:
            status, error = "FAILED", str(e)
            self.bump("errors")
            logger.exception("job {} failed", name)
        await self._log_run(name, started, utcnow(), status, error, trace)

    async def _log_run(
        self,
        name: str,
        started: datetime,
        finished: datetime,
        status: str,
        error: str | None,
        trace: str,
    ) -> None:
        try:
            async with self.sessions() as s:
                s.add(
                    JobRunRow(
                        job_name=name,
                        started_ts=started,
                        finished_ts=finished,
                        status=status,
                        error=error,
                        trace_id=trace,
                    )
                )
                await s.commit()
        except Exception:
            logger.exception("job_run persist failed for {}", name)
