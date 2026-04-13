"""No-network tests for market stress / bounce overlay."""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals.market_reversal_overlay import (
    apply_overlay_to_composite,
    build_market_reversal_overlay,
    feature_row_from_series,
    _rule_stress,
)


def _synth_series(n: int = 300, seed: int = 42) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    ix = pd.date_range("2020-01-01", periods=n, freq="B")
    spy = pd.Series(100 + np.cumsum(rng.normal(0, 0.8, n)), index=ix)
    vix = pd.Series(15 + rng.normal(0, 2, n).clip(10, 50), index=ix)
    return spy, vix


def test_feature_row_from_series_returns_dict():
    spy, vix = _synth_series()
    f = feature_row_from_series(spy, vix)
    assert f is not None
    assert "spy_ret_5" in f and "vix_level" in f


def test_rule_stress_high_when_crash():
    f = {
        "spy_ret_1": -0.02,
        "spy_ret_5": -0.05,
        "spy_ret_20": -0.08,
        "spy_dd_20h": -0.08,
        "spy_dist_ma200": -0.1,
        "spy_rsi_14": 28.0,
        "vix_level": 32.0,
        "vix_ret_5": 0.1,
        "vix_z_20": 1.5,
        "rv10_spy": 28.0,
    }
    s = _rule_stress(f)
    assert s >= 55


def test_build_overlay_disabled():
    cfg = {"market_reversal_overlay": {"enabled": False}}
    out = build_market_reversal_overlay(
        cfg,
        vix=20.0,
        real_yield=None,
        market_regime_data=None,
        close_spy=None,
        vix_series=None,
    )
    assert out.get("enabled") is False


def test_apply_overlay_delta():
    o = {"enabled": True, "composite_buy_delta": -5.0}
    cb, cf = apply_overlay_to_composite(70.0, 68.0, o, apply_adjustment=True)
    assert cb == 65.0
    assert cf == 63.0
