from signals.recheck_level import recheck_level, recheck_price


def test_level_prefers_ma50_then_ma200():
    assert recheck_price(260.0, 255.0, 240.0) == (255.0, "50-day average")
    assert recheck_price(250.0, 255.0, 242.7) == (242.7, "200-day average")
    assert recheck_price(240.0, 255.0, 242.7) is None


def test_recheck_has_stop_and_max_loss_and_skips_buys():
    closes = [250 + (i % 2) * 2 for i in range(20)]
    r = recheck_level(260.0, 255.0, 240.0, closes, gates_passed=3, gates_total=4)
    assert r["price"] == 255.0 and r["stop"] == 251.0 and r["max_loss_pct"] == 1.6
    assert r["note"].startswith("Not a BUY") and r["gates"] == "3/4 gates pass"
    assert recheck_level(260.0, 255.0, 240.0, closes, signal="BUY") is None
    below = recheck_level(230.0, 255.0, 242.7, closes)
    assert below["price"] is None and "below its 50- and 200-day" in below["note"]
