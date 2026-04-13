"""Tests for unified evaluation harness and walk-forward helpers."""
from __future__ import annotations

import pandas as pd

from signals.evaluation_harness import (
    _baseline_ma200,
    _forward_return_pct,
    summarize_vs_baselines,
)
from signals.probability_calibration import calibrate_probability
from signals.walk_forward_cv import purged_walk_forward_folds, tune_buy_min


def test_forward_return_pct():
    close = pd.Series([100.0, 110.0, 105.0])
    assert _forward_return_pct(close, 0, 1) == 10.0
    assert _forward_return_pct(close, 0, 3) is None


def test_baseline_ma200():
    # Need t_idx >= 200 for MA200 at signal bar
    close = pd.Series([1.0] * 200 + [100.0, 110.0])
    assert _baseline_ma200(close, 200, 1) == 10.0
    # Below MA200 → flat (no long exposure)
    close2 = pd.Series([1.0] * 200 + [0.5, 0.55])
    assert _baseline_ma200(close2, 200, 1) == 0.0


def test_summarize_vs_baselines():
    rows = [
        {"fwd_63d_pct": 5.0, "composite_buy": 75.0, "baseline_ma200_fwd_63d_pct": 4.0},
        {"fwd_63d_pct": -2.0, "composite_buy": 50.0, "baseline_ma200_fwd_63d_pct": 1.0},
    ]
    s = summarize_vs_baselines(rows, horizon=63, buy_min=70.0)
    assert s["n"] == 2
    assert s["mean_fwd_when_composite_ge_buy_min"] == 5.0


def test_purged_folds_yield():
    from datetime import date, timedelta

    d0 = date(2020, 1, 1)
    dates = [(d0 + timedelta(days=i)).isoformat() for i in range(200)]
    folds = list(
        purged_walk_forward_folds(
            dates,
            train_bars=50,
            test_bars=10,
            purge_bars=20,
            step_bars=30,
        )
    )
    assert len(folds) >= 1
    tr, te = folds[0]
    assert len(tr) == 50
    assert set(tr) & set(te) == set()


def test_tune_buy_min():
    rows = [
        {"fwd_63d_pct": 10.0, "composite_buy": 80.0},
        {"fwd_63d_pct": 8.0, "composite_buy": 72.0},
        {"fwd_63d_pct": -5.0, "composite_buy": 65.0},
    ]
    bm, st = tune_buy_min(rows, horizon_key="fwd_63d_pct", candidates=(60.0, 70.0, 80.0))
    assert bm in (60.0, 70.0, 80.0)
    assert st.get("n") is not None


def test_platt_identity():
    art = {"method": "platt", "short": {"a": 1.0, "b": 0.0}}
    assert calibrate_probability(0.6, "short", art) == calibrate_probability(0.6, "short", art)
