"""Quant$warm dashboard — tabbed main window over DashboardStore."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from quant_swarm.core.schemas import ChatRole, Decision, InfoCard

from .store import DashboardStore


def _fmt_ts(ts: datetime | None) -> str:
    return ts.strftime("%H:%M:%S") if ts else "-"


def _fill(table: QTableWidget, headers: list[str], rows: list[list[str]]) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            item = QTableWidgetItem(cell)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(i, j, item)
    table.resizeColumnsToContents()
    table.setAlternatingRowColors(True)
    table.horizontalHeader().setStretchLastSection(True)


class CardDetailDialog(QDialog):
    """Pretty-prints a resolved InfoCard payload."""

    def __init__(self, detail: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"card {detail.get('card_id', '')}")
        self.resize(560, 480)
        text = QPlainTextEdit(readOnly=True)
        text.setPlainText(json.dumps(detail, ensure_ascii=False, indent=2, default=str))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(text)
        lay.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self, store: DashboardStore) -> None:
        super().__init__()
        self.store = store
        self.setWindowTitle("Quant$warm Dashboard")
        self.resize(1100, 720)

        self.tabs = QTabWidget()
        self._build_chat_tab()
        self._build_agents_tab()
        self._build_cards_tab()
        self._build_decisions_tab()
        self._build_portfolio_tab()
        self._build_risk_tab()
        self.setCentralWidget(self.tabs)

        store.on_change(self.refresh_all)
        self._db_timer = QTimer(self)
        self._db_timer.setInterval(5000)
        self._db_timer.timeout.connect(self.refresh_portfolio)
        self.refresh_all()

    # -- tabs ------------------------------------------------------------
    def _build_chat_tab(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.txt_chat = QTextBrowser()
        self.txt_chat.setOpenExternalLinks(False)
        lay.addWidget(self.txt_chat)
        bottom = QHBoxLayout()
        self.edit_chat = QLineEdit()
        self.edit_chat.setPlaceholderText("给决策 AI 下达任务，如：帮我看看茅台能不能加仓")
        self.edit_chat.returnPressed.connect(self._send_chat)
        btn = QPushButton("Send")
        btn.clicked.connect(self._send_chat)
        bottom.addWidget(self.edit_chat, 1)
        bottom.addWidget(btn)
        lay.addLayout(bottom)
        self.tabs.addTab(w, "Chat")

    def _build_agents_tab(self) -> None:
        self.tbl_agents = QTableWidget()
        self.tabs.addTab(self.tbl_agents, "Agents")

    def _build_cards_tab(self) -> None:
        split = QSplitter(Qt.Orientation.Horizontal)
        self.tbl_cards = QTableWidget()
        self.tbl_cards.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_cards.itemSelectionChanged.connect(self._show_selected_card)
        self.txt_card = QPlainTextEdit(readOnly=True)
        split.addWidget(self.tbl_cards)
        split.addWidget(self.txt_card)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        self.tabs.addTab(split, "Cards")

    def _build_decisions_tab(self) -> None:
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tbl_decisions = QTableWidget()
        self.tbl_decisions.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_decisions.itemSelectionChanged.connect(self._show_selected_decision)
        self.btn_refs = QPushButton("Open referenced cards")
        self.btn_refs.clicked.connect(self._open_refs)
        lay.addWidget(self.tbl_decisions)
        lay.addWidget(self.btn_refs)
        self.txt_decision = QPlainTextEdit(readOnly=True)
        split.addWidget(left)
        split.addWidget(self.txt_decision)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.tabs.addTab(split, "Decisions")

    def _build_portfolio_tab(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.lbl_cash = QLabel("cash: -")
        self.lbl_equity = QLabel("equity: -")
        self.lbl_updated = QLabel("")
        top.addWidget(self.lbl_cash)
        top.addWidget(self.lbl_equity)
        top.addStretch(1)
        top.addWidget(self.lbl_updated)
        lay.addLayout(top)
        self.tbl_positions = QTableWidget()
        lay.addWidget(self.tbl_positions)
        self.tbl_fills = QTableWidget()
        lay.addWidget(QLabel("Fills"))
        lay.addWidget(self.tbl_fills)
        self.tabs.addTab(w, "Portfolio")

    def _build_risk_tab(self) -> None:
        self.tbl_risk = QTableWidget()
        self.tabs.addTab(self.tbl_risk, "Risk")

    # -- refresh ----------------------------------------------------------
    def refresh_all(self) -> None:
        self.refresh_chat()
        self.refresh_agents()
        self.refresh_cards()
        self.refresh_decisions()
        self.refresh_risk()

    def refresh_chat(self) -> None:
        parts = []
        for m in self.store.chat:
            if m.role == ChatRole.USER:
                who = "<b>我</b>"
            else:
                who = f"<b>{m.expert or 'system'}</b>"
            refs = (
                f'<br/><small>refs: {", ".join(m.refs)}</small>' if m.refs else ""
            )
            content = m.content.replace("\n", "<br/>")
            parts.append(
                f"<p><small>{_fmt_ts(m.ts)}</small> {who}<br/>{content}{refs}</p>"
            )
        self.txt_chat.setHtml("".join(parts) or "<i>no messages yet</i>")
        bar = self.txt_chat.verticalScrollBar()
        bar.setValue(bar.maximum())

    def refresh_agents(self) -> None:
        now = datetime.now(UTC)
        rows = []
        for name in sorted(self.store.heartbeats):
            hb = self.store.heartbeats[name]
            ts = hb.ts if hb.ts.tzinfo else hb.ts.replace(tzinfo=UTC)
            age = f"{(now - ts).total_seconds():.0f}s"
            rows.append([name, str(hb.state), _fmt_ts(ts), age, json.dumps(hb.metrics)])
        _fill(self.tbl_agents, ["agent", "state", "last hb", "age", "metrics"], rows)

    def refresh_cards(self) -> None:
        self._card_rows = list(self.store.cards)
        _fill(
            self.tbl_cards,
            ["time", "kind", "symbols", "agent", "source"],
            [
                [
                    _fmt_ts(c.asof),
                    str(c.kind),
                    ",".join(c.symbols),
                    c.agent,
                    c.source,
                ]
                for c in self._card_rows
            ],
        )

    def refresh_decisions(self) -> None:
        self._decision_rows = list(self.store.decisions)
        _fill(
            self.tbl_decisions,
            ["time", "symbol", "action", "qty", "weight", "model"],
            [
                [
                    _fmt_ts(d.ts),
                    d.symbol,
                    str(d.action),
                    str(d.qty or ""),
                    f"{d.target_weight:.2f}" if d.target_weight is not None else "",
                    (d.llm or {}).get("model", "policy"),
                ]
                for d in self._decision_rows
            ],
        )

    def refresh_risk(self) -> None:
        _fill(
            self.tbl_risk,
            ["time", "level", "code", "symbols", "veto", "message"],
            [
                [
                    _fmt_ts(e.ts),
                    str(e.level),
                    e.code,
                    ",".join(e.symbols),
                    "veto" if e.veto else "",
                    e.message,
                ]
                for e in self.store.risk_events
            ],
        )

    @asyncSlot()
    async def refresh_portfolio(self) -> None:
        acc = await self.store.account()
        if acc:
            self.lbl_cash.setText(f"cash: {acc.cash:,.0f}")
            self.lbl_equity.setText(f"equity: {acc.equity:,.0f}")
            self.lbl_updated.setText(f"updated {_fmt_ts(acc.updated_ts)}")
        positions = await self.store.positions()
        last = self._last_closes()
        _fill(
            self.tbl_positions,
            ["symbol", "qty", "avg_cost", "last", "mkt_val", "unrealized"],
            [
                [
                    p.symbol,
                    str(p.qty),
                    f"{p.avg_cost:.2f}",
                    f"{last.get(p.symbol, 0):.2f}",
                    f"{p.qty * last.get(p.symbol, p.avg_cost):,.0f}",
                    f"{p.qty * (last.get(p.symbol, p.avg_cost) - p.avg_cost):+,.0f}",
                ]
                for p in positions
                if p.qty
            ],
        )
        _fill(
            self.tbl_fills,
            ["time", "order", "status", "qty", "price", "broker"],
            [
                [
                    _fmt_ts(f.ts),
                    f.order_id[-8:],
                    str(f.status),
                    str(f.filled_qty),
                    f"{f.avg_price:.2f}",
                    f.broker,
                ]
                for f in self.store.fills
            ],
        )

    def _last_closes(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for c in self.store.cards:
            if str(c.kind) != "market":
                continue
            closes = (c.payload or {}).get("closes") or []
            for s in c.symbols:
                if closes and s not in out:
                    out[s] = closes[-1]
        return out

    # -- detail panes ------------------------------------------------------
    def _selected_index(self, table: QTableWidget) -> int | None:
        rows = {i.row() for i in table.selectedIndexes()}
        return next(iter(rows)) if rows else None

    def _show_selected_card(self) -> None:
        idx = self._selected_index(self.tbl_cards)
        if idx is None or idx >= len(self._card_rows):
            return
        card: InfoCard = self._card_rows[idx]
        digest = {"card_id": card.card_id, "agent": card.agent, "kind": str(card.kind)}
        digest.update(card.model_dump(mode="json", exclude=set(digest)))
        self.txt_card.setPlainText(json.dumps(digest, ensure_ascii=False, indent=2))

    def _show_selected_decision(self) -> None:
        idx = self._selected_index(self.tbl_decisions)
        if idx is None or idx >= len(self._decision_rows):
            return
        d: Decision = self._decision_rows[idx]
        self.txt_decision.setPlainText(
            json.dumps(d.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )

    @asyncSlot()
    async def _open_refs(self) -> None:
        idx = self._selected_index(self.tbl_decisions)
        if idx is None or idx >= len(self._decision_rows):
            return
        for ref in self._decision_rows[idx].card_refs:
            detail = await self.store.card_detail(ref)
            if detail:
                CardDetailDialog(detail, self).exec()

    @asyncSlot()
    async def _send_chat(self) -> None:
        text = self.edit_chat.text().strip()
        if not text:
            return
        self.edit_chat.clear()
        await self.store.send_chat(text)
