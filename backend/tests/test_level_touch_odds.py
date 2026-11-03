import numpy as np
import pandas as pd

from signals.horizon_entry_calculator import build_all_horizons_payload
from signals.level_touch_odds import attach_level_touch_odds, level_touch_stats


def _series(n=600):
    rng = np.random.default_rng(0)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return c, c * (1 - np.abs(rng.normal(0, 0.01, n)))


def test_deeper_levels_hit_less_often_and_later():
    c, l = _series()
    near, far = level_touch_stats(c, l, 2, 63), level_touch_stats(c, l, 15, 63)
    assert near[0] > far[0] and near[1] < far[1]


def test_short_history_returns_none():
    c, l = _series(100)
    assert level_touch_stats(c, l, 5, 63) is None


def test_attach_sets_odds_on_levels_below_spot():
    c, l = _series()
    df = pd.DataFrame({"Close": c, "Low": l})
    payload = {"medium": {"entry_zone": {"levels": [{"price": c[-1] * 0.95}, {"price": c[-1] * 1.01}]}}}
    attach_level_touch_odds(payload, df, float(c[-1]))
    below, above = payload["medium"]["entry_zone"]["levels"]
    assert 0 < below["touch_pct"] < 100 and below["window_sessions"] == 63
    assert above["touch_pct"] == 100 and above["median_days"] == 0


def test_medium_band_capped_at_spot_and_narrow_when_below_ma50():
    p = 202.06
    o = build_all_horizons_payload(
        current_price=p, ma50=221.44, ma200=204.17, fair_value=291.08, support_level=199.0,
        vwap=p, atr=7.5, week52_low=86.6, rsi=30, resistance_level=p * 1.1, volume_ratio=1,
        st_ml_prob=31, mt_ml_prob=31, lt_ml_prob=31, regime_bull_pct=0, pattern_score=43,
        options_sentiment_score=50, insider_activity_score=50, fundamentals_score=70, ticker="NVDA",
    )
    ez = o["medium"]["entry_zone"]
    assert ez["high"] <= p * 1.005
    assert (ez["high"] - ez["low"]) / p <= 0.121
