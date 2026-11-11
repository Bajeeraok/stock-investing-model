import math

from signals.stock_day_range import build_day_range, ewma_sigmas, scorecard


def _series(n=80, vol=0.02):
    closes, p = [], 100.0
    for i in range(n):
        p *= math.exp(vol * (1 if i % 2 else -1))
        closes.append(p)
    return closes, [f"2026-01-{i:03d}" for i in range(n)]


def test_next_session_band_is_symmetric_and_vol_sized():
    c, d = _series()
    r = build_day_range(c, d, levels=[{"label": "Swing band top", "price": c[-1] * 0.97}])
    assert r["phase"] == "next_session" and r["p_close_green"] is None
    assert r["close_low"] < r["ref_close"] < r["close_high"]
    assert 1.5 < r["sigma_pct"] < 2.5
    lv = r["levels"][0]
    assert lv["side"] == "below" and 0.05 < lv["p_reach"] < 0.6 and not lv["touched"]


def test_intraday_touched_level_and_green_odds():
    c, d = _series()
    s = {"last": c[-1] * 1.03, "high": c[-1] * 1.035, "low": c[-1] * 0.99, "minutes_since_open": 200}
    r = build_day_range(c, d, session=s, levels=[{"label": "band", "price": c[-1]}, {"label": "far", "price": c[-1] * 1.3}])
    assert r["phase"] == "intraday" and r["p_close_green"] > 0.9
    by = {x["label"]: x for x in r["levels"]}
    assert by["band"]["touched"] and by["band"]["p_reach"] < 0.5
    assert by["far"]["p_reach"] < 0.05
    assert r["close_high"] - r["close_low"] < (c[-1] * 0.04) * 2


def test_scorecard_and_short_history():
    c, d = _series()
    sc = scorecard(c, d)
    assert sc["sessions"] >= 20 and 0 <= sc["coverage_pct"] <= 100
    assert build_day_range(c[:10], d[:10]) is None
    assert ewma_sigmas([100.0])[0] is None


def test_band50_inside_band80():
    import math
    from signals.stock_day_range import build_day_range

    closes = [100 * math.exp(0.02 * ((-1) ** i)) for i in range(80)]
    dates = [f"d{i}" for i in range(80)]
    for session in (None, {"last": 101.0, "minutes_since_open": 120, "low": 99.0, "high": 102.0}):
        r = build_day_range(closes, dates, session=session)
        assert r["close_low"] < r["close_low50"] < r["close_mid"] < r["close_high50"] < r["close_high"]


def test_reach_ladder_matches_level_odds():
    import math
    from signals.stock_day_range import build_day_range

    closes = [100 * math.exp(0.02 * ((-1) ** i)) for i in range(80)]
    dates = [f"d{i}" for i in range(80)]
    session = {"last": 101.0, "minutes_since_open": 120, "low": 100.5, "high": 101.5}
    r = build_day_range(closes, dates, session=session)
    lad = r["ladder"]
    assert [x["p"] for x in lad] == [0.75, 0.5, 0.25, 0.1]
    assert lad[0]["dip"] > lad[1]["dip"] > lad[2]["dip"] and lad[0]["pop"] < lad[2]["pop"]
    chk = build_day_range(closes, dates, session=session, levels=[{"label": "x", "price": lad[1]["dip"]}])
    assert abs(chk["levels"][0]["p_reach"] - 0.5) <= 0.02
    pre = build_day_range(closes, dates)
    assert len(pre["ladder"]) == 4 and pre["ladder"][2]["dip"] < 100 * math.exp(0.02 * ((-1) ** 79))
