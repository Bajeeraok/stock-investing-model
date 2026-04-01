"""Regime labeling for backtests (SPY vs SMA)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.backtest_regime import (
    aggregate_walk_forward_by_regime,
    regime_label_at,
    summarize_regime_distribution,
)


def test_regime_label_uptrend_is_bull():
    idx = pd.date_range("2020-01-01", periods=250, freq="B")
    px = np.linspace(100, 200, len(idx))
    s = pd.Series(px, index=idx)
    assert regime_label_at(s, 220, 200) == "bull"


def test_summarize_counts():
    idx = pd.date_range("2020-01-01", periods=260, freq="B")
    px = np.linspace(100, 130, len(idx))
    s = pd.Series(px, index=idx)
    out = summarize_regime_distribution(s, 200, 250, 200)
    assert out["bars_counted"] == 50
    assert out["pct_trading_days_bull"] == 100.0


def test_aggregate_walk_forward_by_regime():
    windows = [
        {"spy_regime": "bull", "results": {3: {"hit_rate": 60.0, "avg_return_pct": 5.0}}},
        {"spy_regime": "bull", "results": {3: {"hit_rate": 50.0, "avg_return_pct": 3.0}}},
        {"spy_regime": "bear", "results": {3: {"hit_rate": 40.0, "avg_return_pct": -1.0}}},
    ]
    agg = aggregate_walk_forward_by_regime(windows, 3)
    assert agg["bull"]["window_count"] == 2
    assert agg["bull"]["avg_hit_rate_pct"] == 55.0
    assert agg["bear"]["window_count"] == 1
