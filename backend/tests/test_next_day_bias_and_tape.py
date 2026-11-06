from datetime import date

import pandas as pd

from signals import premarket_engine as pe
from signals.market_catalysts import _live_tape_drivers
from signals.next_day_bias import _bias_from_stats, _state


def _row():
    return pd.Series({"close": 100.0, "MA20": 101.0, "MA50": 102.0, "RSI": 50.0})


def test_vol_regime_uses_20d_vs_60d_daily_vol():
    assert _state(_row(), 0.02, 0.012)[2] == "high"
    assert _state(_row(), 0.008, 0.012)[2] == "low"
    assert _state(_row(), 0.012, 0.012)[2] == "normal"
    assert _state(_row(), 0.02, None)[2] == "normal"


def _stats(state_pct, state_n, other_pct=54.0, other_n=1000):
    return {"a|neutral|normal": {"n": state_n, "pct_green": state_pct, "avg_return_pct": 0.1, "std_return_pct": 1.0},
            "b|neutral|normal": {"n": other_n, "pct_green": other_pct, "avg_return_pct": 0.0, "std_return_pct": 1.0}}


def test_marginal_green_rate_is_not_bullish():
    r = _bias_from_stats("a|neutral|normal", _stats(56.7, 300))
    assert r["bias"] == "Neutral" and r["edge_strength"] == "none"
    assert r["n"] == 300 and 54 < r["base_pct_green"] < 55


def test_clear_edge_over_base_rate_is_bullish():
    r = _bias_from_stats("a|neutral|normal", _stats(66.0, 400))
    assert r["bias"] == "Bullish" and r["edge_strength"] == "moderate"


def test_missing_or_thin_state_has_no_edge():
    assert _bias_from_stats("zzz", _stats(70.0, 400))["edge_strength"] == "none"
    r = _bias_from_stats("a|neutral|normal", _stats(80.0, 20))
    assert r["bias"] == "Neutral" and r["pct_green"] is None


def test_prior_session_move_is_flagged_and_unscored(monkeypatch):
    monkeypatch.setattr(pe, "_session_ref_date", lambda: date(2026, 11, 6))
    mk = lambda: pe.PreMarketSignal(name="NVDA", score=-1.0, weight=0.01, raw_value="-9.26%", direction="Bearish", confidence=1.0)
    s = pe._mark_stale(mk(), date(2026, 11, 5))
    assert s.stale and s.confidence == 0 and s.score == 0 and s.raw_value == "-9.26% (Nov 5)"
    fresh = pe._mark_stale(mk(), date(2026, 11, 6))
    assert not fresh.stale and fresh.confidence == 1.0 and fresh.as_of == "2026-11-06"
    comp, _ = pe._confidence_weighted_composite([s, fresh])
    assert comp == -1.0


def test_live_tape_puts_stale_last_and_flagged():
    pm = {"signals": [
        {"name": "Asia close (Nikkei 225)", "raw_value": "-1.79% (Nov 5)", "score": 0.0, "stale": True, "as_of": "2026-11-05"},
        {"name": "Nasdaq Futures (NQ=F)", "raw_value": "+1.54%", "score": 0.9, "direction": "Bullish"},
    ]}
    out = _live_tape_drivers(pm)
    assert [d["name"] for d in out] == ["Nasdaq Futures (NQ=F)", "Asia close (Nikkei 225)"]
    assert out[1]["stale"] is True and out[1]["direction"] == "Neutral"
