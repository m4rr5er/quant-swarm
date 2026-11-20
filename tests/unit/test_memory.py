"""MemoryFile — bounded agent-managed memory (hermes-style)."""

import pytest

from quant_swarm.core.memory import MemoryFile, MemoryFullError, expert_memory, user_memory


@pytest.fixture
def mem(tmp_path):
    return MemoryFile(tmp_path / "experts" / "investor.md", max_chars=200)


def test_empty_load(mem) -> None:
    assert mem.load() == ""
    assert mem.sections() == {}


def test_set_and_reload(mem) -> None:
    mem.set("偏好", "用户偏好白酒板块")
    mem.set("纪律", "单票不超 20%")
    text = mem.load()
    assert "## 偏好" in text and "白酒" in text
    # reload from disk — persistence across processes
    again = MemoryFile(mem.path, max_chars=200)
    assert again.sections()["纪律"] == "单票不超 20%"


def test_set_replaces_existing(mem) -> None:
    mem.set("a", "one")
    mem.set("a", "two")
    assert mem.sections()["a"] == "two"


def test_remove(mem) -> None:
    mem.set("a", "x")
    assert mem.remove("a") is True
    assert mem.remove("a") is False
    assert "a" not in mem.sections()


def test_bounded_write_raises(mem) -> None:
    mem.set("big", "x" * 150)
    with pytest.raises(MemoryFullError):
        mem.set("overflow", "y" * 150)


def test_named_files(tmp_path) -> None:
    assert user_memory(tmp_path).path.name == "USER.md"
    assert expert_memory(tmp_path, "quant").path.name == "quant.md"
    assert expert_memory(tmp_path, "quant").path.parent.name == "experts"
