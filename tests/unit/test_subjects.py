from quant_swarm.core import subjects as sub


def test_builders() -> None:
    assert sub.ctrl_collect("market_data") == "qs.ctrl.collect.market_data"
    assert sub.cards_market("600519.SH") == "qs.cards.market.600519.SH"
    assert sub.heartbeat("brain") == "qs.heartbeat.brain"
    assert sub.DECISIONS == "qs.decisions"


def test_exact_match() -> None:
    assert sub.match_subject("qs.decisions", "qs.decisions")
    assert not sub.match_subject("qs.decisions", "qs.orders")


def test_star_matches_one_token() -> None:
    assert sub.match_subject("qs.ctrl.collect.*", "qs.ctrl.collect.market_data")
    assert not sub.match_subject("qs.ctrl.collect.*", "qs.ctrl.collect")
    assert not sub.match_subject("qs.ctrl.collect.*", "qs.ctrl.collect.a.b")


def test_gt_matches_tail() -> None:
    assert sub.match_subject("qs.cards.>", "qs.cards.market.600519.SH")
    assert sub.match_subject("qs.cards.>", "qs.cards.market")
    assert not sub.match_subject("qs.cards.>", "qs.alerts.events")
    assert not sub.match_subject("qs.>", "other.topic")


def test_gt_must_be_last() -> None:
    assert not sub.match_subject("qs.>.x", "qs.a.b.x")
