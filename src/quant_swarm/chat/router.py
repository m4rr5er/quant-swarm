"""Rule-based task router: user message -> which expert(s) handle it.

Scoring is keyword-count based; a cheap LLM fallback and the M5b
co-signing protocol plug in here later. Compound tasks (both domains
score) resolve to the primary expert for now — the routing metadata is
kept on the ExpertTask so the co-sign upgrade needs no new plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass

INVESTOR_KEYS = (
    "买", "卖", "加仓", "减仓", "清仓", "建仓", "仓位", "持仓", "持有",
    "目标价", "估值", "基本面", "财报", "市值", "分红", "风险",
    "组合", "行情", "走势", "新闻", "政策", "板块", "大盘", "资金流",
    "主力", "buy", "sell", "position", "portfolio",
)

QUANT_KEYS = (
    "回测", "策略", "参数", "均线", "金叉", "死叉", "因子", "胜率",
    "夏普", "滑点", "网格", "止损", "信号", "模型", "优化", "指标",
    "收益曲线", "最大回撤", "backtest", "strategy", "signal", "drawdown",
)


@dataclass
class RouteResult:
    expert: str            # "investor" | "quant"
    score_investor: int
    score_quant: int
    compound: bool = False  # both domains matched -> M5b co-sign


def classify(text: str) -> RouteResult:
    t = text.lower()
    si = sum(1 for k in INVESTOR_KEYS if k in t)
    sq = sum(1 for k in QUANT_KEYS if k in t)
    compound = si > 0 and sq > 0
    if sq > si:
        expert = "quant"
    else:
        expert = "investor"  # default & tie-break: investment expert
    return RouteResult(expert=expert, score_investor=si, score_quant=sq, compound=compound)
