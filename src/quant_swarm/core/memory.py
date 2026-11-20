"""Bounded, agent-managed memory files (hermes-style).

A memory file is markdown of ``## <title>`` sections plus an optional
preamble. Agents mutate it through a small tool surface (add/patch/
remove/list); writes are rejected once the file exceeds ``max_chars``
so the agent must consolidate first — bounded memory, no silent growth.

Layout under ``Settings.memory_dir`` (default ``memory/``)::

    memory/USER.md                  user profile — read by all experts
    memory/experts/<name>.md        expert working notes
    memory/agents/<name>.md         worker operational knowledge
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SECTION = re.compile(r"^## (.+)$", re.MULTILINE)


class MemoryFullError(RuntimeError):
    """Write would exceed the file's char budget — consolidate first."""


@dataclass
class MemoryFile:
    path: Path
    max_chars: int = 2200
    preamble: str = field(default="", repr=False)

    def load(self) -> str:
        """Return the raw file (what gets injected into the system prompt)."""
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8").strip()

    def sections(self) -> dict[str, str]:
        """Parse ``## title`` sections into {title: body}."""
        text = self.load()
        if not text:
            return {}
        parts = _SECTION.split(text)
        self.preamble = parts[0].strip()
        out: dict[str, str] = {}
        for i in range(1, len(parts) - 1, 2):
            out[parts[i].strip()] = parts[i + 1].strip()
        return out

    def set(self, title: str, body: str) -> None:
        """Add or replace a section."""
        secs = self.sections()
        secs[title.strip()] = body.strip()
        self._flush(secs)

    def remove(self, title: str) -> bool:
        secs = self.sections()
        if title.strip() not in secs:
            return False
        del secs[title.strip()]
        self._flush(secs)
        return True

    def _flush(self, secs: dict[str, str]) -> None:
        head = f"{self.preamble}\n\n" if self.preamble else ""
        text = head + "\n\n".join(f"## {t}\n{b}" for t, b in secs.items())
        if len(text) > self.max_chars:
            raise MemoryFullError(
                f"{self.path.name} would exceed {self.max_chars} chars "
                f"({len(text)}); consolidate sections first"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text.strip() + "\n", encoding="utf-8")


def memory_dir(base: str | Path) -> Path:
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_memory(base: str | Path) -> MemoryFile:
    return MemoryFile(memory_dir(base) / "USER.md", max_chars=1400)


def expert_memory(base: str | Path, name: str) -> MemoryFile:
    return MemoryFile(memory_dir(base) / "experts" / f"{name}.md", max_chars=2200)


def agent_memory(base: str | Path, name: str) -> MemoryFile:
    return MemoryFile(memory_dir(base) / "agents" / f"{name}.md", max_chars=1600)
