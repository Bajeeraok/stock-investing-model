import pandas as pd

from signals.forward_tracking_metrics import build_error_summary, build_prob_calibration
from signals.level_touch_odds import compact_level_odds, score_level_odds


def _rec(ret, target=110.0, stop=95.0, fwd=None, prob=None):
    return {
        "forward_status": "complete",
        "actual_return_pct": ret,
        "close_at_signal": 100.0,
        "st_target_at_signal": target,
        "st_stop_at_signal": stop,
        "close_at_forward": fwd if fwd is not None else 100.0 * (1 + ret / 100),
        "hit_st_target": ret >= 10,
        "hit_st_stop": ret <= -5,
        "ml_short_prob": prob,
    }


def test_error_summary_bias_and_range():
    s = build_error_summary([_rec(2.0), _rec(-6.0), _rec(12.0)])
    assert s["n"] == 3
    assert s["avg_expected_pct"] == 10.0
    assert s["mae_pp"] == round((8 + 16 + 2) / 3, 2)
    assert s["bias_pp"] == round((-8 - 16 + 2) / 3, 2)
    assert s["within_range_pct"] == round(100 / 3, 1)


def test_prob_calibration_normalizes_0_1():
    rows = [_rec(1.0, prob=0.65), _rec(-1.0, prob=65), _rec(2.0, prob=0.3)]
    c = build_prob_calibration(rows)
    assert c["n"] == 3
    b = {x["range"]: x for x in c["buckets"]}
    assert b["60–70%"]["actual_up_pct"] == 50.0
    assert b["0–40%"]["actual_up_pct"] == 100.0


def test_level_odds_log_and_score():
    closes = [100 + (i % 10) for i in range(400)]
    df = pd.DataFrame({"close": closes, "low": [c - 3 for c in closes]})
    lo = compact_level_odds(df, 100.0)
    assert lo and lo["levels"][0]["drop_pct"] == 2.0 and "w20" in lo["levels"][0]
    dates = [f"d{i:02d}" for i in range(30)]
    rows = {d: {"AAA": {"close": 100.0, "low": 99.0}} for d in dates}
    rows["d00"]["AAA"]["level_odds"] = {"levels": [{"price": 98.0, "w20": {"p": 70}, "w63": {"p": 90}}]}
    rows["d05"]["AAA"]["low"] = 97.5
    out = score_level_odds(dates, rows)
    assert out["pooled"]["20"]["actual_hit_pct"] == 100.0
    assert out["pooled"]["63"]["actual_hit_pct"] == 100.0
    assert out["pending"] == 0
