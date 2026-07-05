"""Tests for swing_backtest simulation."""
from __future__ import annotations

import pandas as pd

from signals.swing_backtest import simulate_swing_trade, summarize_swing_backtest


def _ohlcv_from_closes(closes: list[float], start: str = "2026-01-02") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
        },
        index=idx,
    )


def test_simulate_hits_t1():
    closes = [100.0] * 5 + [101.0, 102.0, 104.0, 105.0]
    df = _ohlcv_from_closes(closes)
    sig_date = df.index[4].strftime("%Y-%m-%d")
    out = simulate_swing_trade(
        df,
        sig_date,
        entry_price=100.0,
        stop=95.0,
        t1=103.0,
        t2=108.0,
        horizon_days=5,
    )
    assert out["hit_t1"] is True
    assert out["exit_reason"] == "t1"
    assert out["verdict"] == "WIN"


def test_simulate_hits_stop():
    closes = [100.0] * 5 + [99.0, 97.0, 94.0]
    df = _ohlcv_from_closes(closes)
    sig_date = df.index[4].strftime("%Y-%m-%d")
    out = simulate_swing_trade(
        df,
        sig_date,
        entry_price=100.0,
        stop=95.0,
        t1=110.0,
        t2=115.0,
        horizon_days=5,
    )
    assert out["hit_stop"] is True
    assert out["verdict"] == "LOSS"


def test_summarize_empty():
    s = summarize_swing_backtest([])
    assert s["n"] == 0
