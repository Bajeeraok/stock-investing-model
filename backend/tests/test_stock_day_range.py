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
