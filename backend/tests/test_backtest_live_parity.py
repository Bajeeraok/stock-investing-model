"""Backtest live-parity context (regime + MRO) — causal, no lookahead."""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals.backtest_live_parity import BacktestLiveContext, composite_with_live_parity


def test_live_context_disabled_when_config_off():
    idx = pd.date_range("2020-01-01", periods=300, freq="B")
    ctx = BacktestLiveContext.prepare(idx, "2y", {"backtest": {"apply_live_adjustments": False}})
    assert ctx.enabled is False


def test_composite_with_live_parity_returns_bounded_score(monkeypatch):
    idx = pd.date_range("2020-01-01", periods=260, freq="B")
    close = pd.Series(np.linspace(100, 150, len(idx)), index=idx)
    cfg = {"backtest": {"apply_live_adjustments": False}}

    def fake_composite_score(*args, **kwargs):
        return {"composite_buy": 72.0, "confluence_score": 70.0}

    monkeypatch.setattr("signals.indicators.composite_score", fake_composite_score)
    monkeypatch.setattr(
        "signals.sector_classifier.get_sector_weights",
        lambda _t: None,
    )
    monkeypatch.setattr(
        "signals.sector_classifier.get_sector_score_bias",
        lambda _t: 0.0,
    )

    score = composite_with_live_parity(close, 200, "SPY", cfg, None)
    assert score is not None
    assert 0 <= score <= 100
