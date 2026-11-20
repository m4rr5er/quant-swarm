"""Rule router — investor/quant/compound classification."""

from quant_swarm.chat.router import classify


def test_investor_task() -> None:
    r = classify("帮我看看茅台能不能加仓")
    assert r.expert == "investor"
    assert r.score_investor > 0


def test_quant_task() -> None:
    r = classify("帮我回测一下双均线策略的参数")
    assert r.expert == "quant"
    assert r.score_quant > 0


def test_compound_flags_both() -> None:
    r = classify("这个仓位的双均线策略信号可靠吗，要减仓吗")
    assert r.compound is True


def test_default_is_investor() -> None:
    r = classify("今天怎么样")
    assert r.expert == "investor"
    assert r.compound is False
