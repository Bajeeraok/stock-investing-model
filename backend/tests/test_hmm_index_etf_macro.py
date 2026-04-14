"""Index ETF macro blend for HMM display probabilities."""
import numpy as np
import pandas as pd
import pytest

from signals.hmm_regime import _apply_major_index_etf_macro, _index_etf_macro_stress


def test_macro_stress_rises_with_drawdown_vix_and_63d():
    idx = pd.date_range("2024-01-01", periods=300, freq="B")
    # Peak then selloff
    vals = np.concatenate(
        [np.linspace(500, 700, 200), np.linspace(700, 560, 100)]
    )
    close = pd.Series(vals, index=idx)
    s, dbg = _index_etf_macro_stress(close, vix=32.0, recent_63d_return_pct=-11.0)
    assert s > 0.35
    assert dbg.get("dd_from_peak_pct") is not None
    assert dbg["dd_from_peak_pct"] < -5


def test_spy_bull_reduced_when_stress_high():
    b, t, r, audit = _apply_major_index_etf_macro(
        0.84,
        0.0,
        0.16,
        ticker="SPY",
        close=None,
        vix=35.0,
        recent_63d_return_pct=-12.0,
    )
    assert audit is not None
    assert audit.get("applied") is True
    assert b < 0.84
    assert b + t + r == pytest.approx(1.0, abs=1e-3)


def test_non_index_ticker_unchanged():
    b, t, r, audit = _apply_major_index_etf_macro(
        0.7,
        0.2,
        0.1,
        ticker="NVDA",
        close=None,
        vix=40.0,
        recent_63d_return_pct=-20.0,
    )
    assert b == 0.7 and t == 0.2 and r == 0.1
    assert audit is None


def test_price_targets_long_stop_index_etf_uses_ma200_cap():
    from signals.price_targets import _horizon_targets

    lv = {
        "current_price": 680.0,
        "ma50": 650.0,
        "ma200": 661.0,
        "low_52w": 508.0,
    }
    h = {"prob": 0.4, "threshold_pct": 12, "horizon_days": 120, "label": "long", "interpretation": "n"}
    out = _horizon_targets(lv, h, "NEUTRAL", "long", ticker="SPY")
    assert out["stop_loss"] == round(max(661.0 * 0.97, 508.0 * 0.97), 2)
    out_nvda = _horizon_targets(lv, h, "NEUTRAL", "long", ticker="NVDA")
    assert out_nvda["stop_loss"] == round(508.0 * 0.97, 2)
