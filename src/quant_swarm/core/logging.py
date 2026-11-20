"""loguru setup — one rolling file per agent plus stderr.

Every log record carries ``extra["trace_id"]``; handlers should
``logger.bind(trace_id=...)`` when processing a bus message so the whole
collect -> decide -> order -> fill chain is greppable by one id.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_FMT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | "
    "{extra[trace_id]} | {name}:{function}:{line} | {message}"
)


def setup_logging(agent: str, log_dir: str = "logs", level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.configure(extra={"trace_id": "-"})
    logger.add(sys.stderr, level=level, format=_FMT)
    logger.add(
        Path(log_dir) / f"{agent}.log",
        level=level,
        format=_FMT,
        rotation="10 MB",
        retention=5,
        enqueue=True,
    )
