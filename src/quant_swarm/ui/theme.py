"""Dashboard look & feel — dark theme + fonts + chat rendering helpers."""

from __future__ import annotations

import html

import markdown as _md

# Fonts — first hit wins. Windows ships YaHei; under WSLg we link
# /mnt/c/Windows/Fonts into ~/.local/share/fonts so the same families
# resolve there too. Noto/WQY cover plain Linux.
FONT_FAMILIES = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "WenQuanYi Micro Hei",
    "PingFang SC",
    "sans-serif",
]

MONO_FAMILIES = ["Cascadia Mono", "JetBrains Mono", "Consolas", "monospace"]

# palette
BG = "#14161b"
PANEL = "#1c1f27"
PANEL2 = "#22252f"
BORDER = "#2e3340"
TEXT = "#e6e8ee"
DIM = "#8b93a3"
ACCENT = "#5b9dff"
USER_BG = "#24344d"
EXPERT_BG = "#22262f"

EXPERT_COLORS = {
    "investor": "#f0a35e",
    "quant": "#5bd0a0",
    "system": "#8b93a3",
}

STYLE = f"""
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; font-size: 13px; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; background: {BG}; }}
QTabBar::tab {{
    background: {BG}; color: {DIM}; padding: 7px 16px;
    border: 1px solid transparent; border-bottom: none;
}}
QTabBar::tab:selected {{ background: {PANEL}; color: {TEXT}; border-color: {BORDER}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QTableWidget, QListWidget, QPlainTextEdit, QTextBrowser, QLineEdit {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 4px;
    selection-background-color: #33415c; selection-color: {TEXT};
}}
QTableWidget {{ gridline-color: {BORDER}; alternate-background-color: {PANEL2}; }}
QHeaderView::section {{
    background: {PANEL2}; color: {DIM}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 5px 8px; text-align: left;
}}
QLineEdit {{ padding: 8px 10px; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QPushButton {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 7px 14px; color: {TEXT};
}}
QPushButton:hover {{ background: #2a2f3c; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #1f2330; }}

QLabel {{ background: transparent; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}

QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""

# QTextBrowser supports a safe subset of HTML/CSS — tables give us the
# bubble look (no border-radius in Qt rich text).
_CHAT_CSS = f"""
body {{ color: {TEXT}; font-family: '{FONT_FAMILIES[0]}'; font-size: 13px; }}
table.msg {{ width: 97%; margin: 6px 0; }}
td.bubble {{ padding: 8px 12px; }}
td.user {{ background: {USER_BG}; }}
td.expert {{ background: {EXPERT_BG}; }}
span.who {{ font-weight: bold; }}
span.ts {{ color: {DIM}; font-size: 11px; }}
div.refs {{ color: {DIM}; font-size: 11px; margin-top: 4px; }}
table.data, table.data th, table.data td {{
    border: 1px solid {BORDER}; border-collapse: collapse; padding: 3px 8px;
}}
table.data th {{ background: {PANEL2}; }}
code {{ background: {PANEL2}; }}
pre {{ background: {PANEL2}; padding: 6px; }}
"""


def md_to_html(text: str) -> str:
    """Render expert markdown (bold/headers/tables/code) to Qt-safe HTML."""
    out = _md.markdown(
        text,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        output_format="html",
    )
    # Qt needs explicit borders on markdown tables.
    return out.replace("<table>", '<table class="data">')


def chat_document(messages: list, fmt_ts) -> str:
    """Full HTML doc for the chat view — bubble rows per message."""
    rows = []
    for m in messages:
        is_user = str(m.role) == "ChatRole.USER" or str(m.role) == "user"
        who = "我" if is_user else (m.expert or "system")
        color = ACCENT if is_user else EXPERT_COLORS.get(who, DIM)
        body = md_to_html(html.escape(m.content))
        refs = (
            f'<div class="refs">refs: {", ".join(html.escape(r) for r in m.refs)}</div>'
            if m.refs
            else ""
        )
        side = "user" if is_user else "expert"
        rows.append(
            f'<table class="msg" cellspacing="0"><tr>'
            f'<td class="bubble {side}">'
            f'<span class="who" style="color:{color}">{html.escape(who)}</span> '
            f'<span class="ts">{fmt_ts(m.ts)}</span>'
            f"{body}{refs}</td></tr></table>"
        )
    empty = (
        '<i style="color:#8b93a3">开始对话 — '
        "例如「现在持仓情况」或「回测一下茅台的双均线」</i>"
    )
    return (
        f"<html><head><style>{_CHAT_CSS}</style></head>"
        f"<body>{''.join(rows) or empty}</body></html>"
    )
