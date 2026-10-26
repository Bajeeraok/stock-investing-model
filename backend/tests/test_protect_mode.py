import numpy as np
import pandas as pd

from signals.confidence_engine import _confidence_to_action
from signals.protect_mode import compute_protect_mode
from signals.regime import get_ml_aware_signal


def _series(start: float, end: float, n: int = 300) -> pd.Series:
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.Series(np.linspace(start, end, n), index=idx)


def test_protect_mode_inactive_in_uptrend():
    out = compute_protect_mode(_series(100, 200), _series(400, 500))
    assert out["available"] and not out["active"]
    assert out["suggested_position_pct"] == 100
    assert out["default_action"] == "HOLD"


def test_protect_mode_active_when_stock_below_ma200():
    c = pd.concat([_series(100, 200, 250), _series(199, 120, 60)])
    c.index = pd.bdate_range("2024-01-01", periods=len(c))
    out = compute_protect_mode(c, _series(400, 500, len(c)))
    assert out["active"] and out["stock_below_ma200"] and not out["spy_risk_off"]
    assert out["suggested_position_pct"] == 50


def test_protect_mode_active_when_spy_risk_off():
    spy = pd.concat([_series(400, 500, 250), _series(499, 380, 60)])
    spy.index = pd.bdate_range("2024-01-01", periods=len(spy))
    out = compute_protect_mode(_series(100, 200, len(spy)), spy)
    assert out["active"] and out["spy_risk_off"]


def test_protect_mode_unavailable_on_short_history():
    out = compute_protect_mode(_series(100, 110, 50), None)
    assert not out["available"] and not out["active"]


def test_low_score_without_ml_is_hold_not_sell():
    assert get_ml_aware_signal(10.0) == "HOLD"
    assert get_ml_aware_signal(80.0) == "WATCH"


def test_low_score_with_healthy_ml_is_hold():
    assert get_ml_aware_signal(10.0, ml_short_prob=0.35) == "HOLD"
    assert get_ml_aware_signal(50.0, ml_short_prob=0.10) == "REDUCE"


def test_confidence_reduce_band_reads_hold():
    assert _confidence_to_action(0.35) == "HOLD / WATCH"
    assert _confidence_to_action(0.10) == "AVOID"
