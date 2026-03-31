"""Signal inversion: thresholds, Hurst clipping, inversion guard."""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.signal_inversion import (
    BucketStats,
    SignalWeights,
    calibrate_thresholds_from_backtest,
    classify_regime,
    compute_hurst_exponent,
    detect_inversion,
)


def test_signal_weights_validate_raises():
    try:
        SignalWeights(momentum=0.5).validate()
    except ValueError as e:
        assert "1.0" in str(e) or "sum" in str(e).lower()
    else:
        raise AssertionError("expected ValueError for bad weights")


def test_bucket_threshold_ordering():
    rng = np.random.default_rng(0)
    n = 80
    scores = np.linspace(10, 90, n)
    ret_3m = scores * 0.05 + rng.normal(0, 2, n)
    df = pd.DataFrame({"score": scores, "return_3m": ret_3m})
    t = calibrate_thresholds_from_backtest(df, horizon="3m")
    assert t.neutral_floor <= t.buy_floor <= t.strong_buy_floor


def test_detect_inversion_strong_vs_weak():
    stats = [
        BucketStats("strong", -5.0, 0.25, 30),
        BucketStats("weak", 10.0, 0.5, 30),
    ]
    out = detect_inversion(stats, min_n=10)
    assert out["inverted"] is True
    assert out.get("primary_strong_vs_weak_inversion") is True


def test_hurst_bounded():
    rng = np.random.default_rng(1)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300))))
    h = compute_hurst_exponent(prices)
    assert 0.01 <= h <= 0.99


def test_classify_regime_brackets():
    assert classify_regime(0.4).value == "mean_reverting"
    assert classify_regime(0.5).value == "random_walk"
    assert classify_regime(0.6).value == "trending"
