"""ui.theme — markdown->HTML chat rendering (no Qt needed)."""

from quant_swarm.core.schemas import ChatMessage, ChatRole
from quant_swarm.ui.theme import chat_document, md_to_html


def test_md_table_becomes_bordered() -> None:
    out = md_to_html("| a | b |\n|---|---|\n| 1 | 2 |")
    assert '<table class="data">' in out
    assert "<td>1</td>" in out


def test_md_bold_and_headers() -> None:
    assert "<strong>不买</strong>" in md_to_html("**不买**")
    assert "<h2" in md_to_html("## 结论")


def test_chat_document_bubbles() -> None:
    msgs = [
        ChatMessage(role=ChatRole.USER, content="茅台能加仓吗"),
        ChatMessage(role=ChatRole.EXPERT, expert="quant", content="**不能**", refs=["c1"]),
    ]
    doc = chat_document(msgs, lambda ts: "10:00")
    assert 'class="bubble user"' in doc
    assert 'class="bubble expert"' in doc
    assert "quant" in doc and "refs: c1" in doc
    # user content escaped, markdown still rendered
    assert "<strong>不能</strong>" in doc


def test_empty_chat_shows_hint() -> None:
    assert "开始对话" in chat_document([], lambda ts: "")
