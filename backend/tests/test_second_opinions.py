import numpy as np
import pandas as pd

from signals.second_opinions import (
    aggregate_second_opinions,
    analyst_score,
    bias_from_label,
    label_from_score,
    technical_ratings,
)


def _df(drift):
    idx = pd.bdate_range("2021-01-01", periods=1250)
    c = pd.Series(100 * np.exp(np.cumsum(np.full(1250, drift))), idx)
    return pd.DataFrame({"close": c, "high": c * 1.01, "low": c * 0.99, "volume": 1e6})


def test_technical_rating_direction():
    up = technical_ratings(_df(0.002))
    down = technical_ratings(_df(-0.002))
    assert up["tv_1d"]["bias"] == "bullish" and up["tv_1d"]["ma"]["sell"] == 0
    assert down["tv_1d"]["bias"] == "bearish" and down["tv_1d"]["ma"]["sell"] > down["tv_1d"]["ma"]["buy"]
    assert up["tv_1w"] is not None and up["tv_1m"] is not None


def test_short_history_is_none():
    assert technical_ratings(_df(0.001).iloc[:20]) == {"tv_1d": None, "tv_1w": None, "tv_1m": None}


def test_labels_and_analyst_score():
    assert label_from_score(0.6) == "Strong Buy" and label_from_score(0.0) == "Neutral"
    assert label_from_score(0.0, analyst=True) == "Hold"
    assert bias_from_label("HOLD") == "neutral" and bias_from_label("CONSIDER TRIM") == "bearish"
    assert bias_from_label("Strong Buy") == "bullish"
    s = analyst_score({"strong_buy": 10, "buy": 10, "hold": 0, "sell": 0, "strong_sell": 0, "total": 20})
    assert s == 0.75


def test_scorecard_like_for_like():
    recs = []
    for i, (lab, ret) in enumerate([("Buy", 2.0), ("Buy", 4.0), ("Sell", -1.0), ("Sell", 1.0)]):
        recs.append({
            "ticker": "AAA", "as_of_date": f"2026-10-0{i + 1}", "horizon_days": 20, "actual_return_pct": ret,
            "excess_return_pct": ret - 1, "our_signal": "HOLD", "data_quality": "ok",
            "forward_status": "complete", "second_opinions": {"tv_1d": lab},
        })
    recs.append({**recs[0], "second_opinions": None, "actual_return_pct": 50.0})
    out = aggregate_second_opinions(recs)
    src = out["by_horizon"]["20"]["sources"]
    assert src["tv_1d"]["by_bias"]["bullish"]["avg_return_pct"] == 3.0
    assert src["tv_1d"]["bull_minus_bear_pct"] == 3.0
    assert src["ours"]["by_bias"]["neutral"]["n"] == 4


def test_analyst_row_keeps_display_name():
    from signals.second_opinions import build_second_opinions

    dist = {"strong_buy": 5, "buy": 5, "hold": 2, "sell": 0, "strong_sell": 0, "total": 12, "bullish_pct": 83.3, "source": "fmp"}
    out = build_second_opinions({}, "AAA", _df(0.001), analyst_dist=dist, include_finnhub=False)
    a = next(o for o in out["opinions"] if o["key"] == "analyst")
    assert a["source"] == "Analyst consensus" and a["provider"] == "fmp"
