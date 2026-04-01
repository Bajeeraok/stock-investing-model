"""Backtest bucket assignment uses MR flip when ACF says mean-reverting."""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.score_interpretation import backtest_bucket_style_at_bar, detect_interpretation_style


def test_for_backtest_buckets_respects_force_mr_when_live_disabled():
    cfg = {
        "score": {
            "interpretation": {
                "enabled": False,
                "apply_to_backtest_buckets": True,
                "force_mean_reverting": ["TEST"],
                "min_bars": 50,
            }
        }
    }
    close = pd.Series(
        np.linspace(100, 120, 200),
        index=pd.date_range("2020-01-01", periods=200, freq="B"),
    )
    style, meta = detect_interpretation_style(close, None, cfg, ticker="TEST", for_backtest_buckets=True)
    assert style == "MEAN_REVERTING"
    assert meta.get("reason") == "force_mean_reverting"


def test_backtest_bucket_style_at_bar_matches_force_mr():
    cfg = {
        "score": {
            "interpretation": {
                "enabled": False,
                "apply_to_backtest_buckets": True,
                "force_mean_reverting": ["ZZZ"],
                "min_bars": 50,
            }
        }
    }
    close = pd.Series(
        np.linspace(100, 120, 200),
        index=pd.date_range("2020-01-01", periods=200, freq="B"),
    )
    assert backtest_bucket_style_at_bar(close, 150, "ZZZ", cfg) == "MEAN_REVERTING"
