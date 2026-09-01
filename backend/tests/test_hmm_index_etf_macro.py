"""Index ETF macro blend for HMM display probabilities."""
import numpy as np
import pandas as pd
import pytest

from signals.hmm_regime import (
    _apply_major_index_etf_macro,
    _build_features_index_etf_vix,
    _index_etf_macro_stress,
)
from signals.horizon_entry_calculator import LongTermInputs, compute_long_term_entry


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


def test_price_targets_long_stop_uses_structural_max_not_tail_only():
    from signals.price_targets import _horizon_targets

    lv = {
        "current_price": 680.0,
        "ma50": 650.0,
        "ma200": 661.0,
        "low_52w": 508.0,
    }
    h = {"prob": 0.4, "threshold_pct": 12, "horizon_days": 120, "label": "long", "interpretation": "n"}
    expected = round(max(661.0 * 0.97, 508.0 * 0.97), 2)
    out = _horizon_targets(lv, h, "NEUTRAL", "long", ticker="SPY")
    assert out["stop_loss"] == expected
    out_nvda = _horizon_targets(lv, h, "NEUTRAL", "long", ticker="NVDA")
    assert out_nvda["stop_loss"] == expected


def test_vix_augmented_feature_matrix_has_expected_width():
    idx = pd.date_range("2018-01-01", periods=400, freq="B")
    close = pd.Series(np.linspace(100.0, 150.0, 400), index=idx)
    vix = pd.Series(np.linspace(14.0, 22.0, 400), index=idx)
    vol = pd.Series(np.ones(400) * 1e6, index=idx)
    arr = _build_features_index_etf_vix(close, vol, vix)
    assert arr is not None
    assert arr.shape[1] == 6  # ret, |ret|, log_vol_change, vix_ret, vix_z, trend_5d


def test_long_term_entry_index_etf_structural_stop_uses_ma200_cap():
    inp = LongTermInputs(
        current_price=500.0,
        fair_value=520.0,
        ma200=480.0,
        week52_low=400.0,
        ml_prob=40.0,
        regime_bull_pct=55.0,
        fundamentals_score=60.0,
        ticker="SPY",
    )
    sig = compute_long_term_entry(inp)
    structural = sig.entry_tiers["structural_invalidation"]["price"]
    assert structural == round(max(480.0 * 0.97, 400.0 * 0.97), 2)
    assert sig.stop_loss < inp.current_price
    assert sig.entry_tiers["structural_invalidation"]["kind"] == "index_structural_floor"


def test_long_term_entry_commodity_etf_matches_index_structural_math():
    inp = LongTermInputs(
        current_price=500.0,
        fair_value=520.0,
        ma200=480.0,
        week52_low=400.0,
        ml_prob=40.0,
        regime_bull_pct=55.0,
        fundamentals_score=60.0,
        ticker="SLV",
    )
    sig = compute_long_term_entry(inp)
    structural = sig.entry_tiers["structural_invalidation"]["price"]
    assert structural == round(max(480.0 * 0.97, 400.0 * 0.97), 2)
    assert sig.stop_loss < inp.current_price
    assert sig.entry_tiers["structural_invalidation"]["kind"] == "commodity_structural_floor"


def test_long_term_entry_single_name_uses_52w_floor():
    inp = LongTermInputs(
        current_price=180.0,
        fair_value=200.0,
        ma200=170.0,
        week52_low=140.0,
        ml_prob=40.0,
        regime_bull_pct=55.0,
        fundamentals_score=60.0,
        ticker="NVDA",
    )
    sig = compute_long_term_entry(inp)
    structural = sig.entry_tiers["structural_invalidation"]["price"]
    assert structural == round(140.0 * 0.95, 2)
    assert sig.stop_loss < inp.current_price
    assert sig.entry_tiers["structural_invalidation"]["kind"] == "52w_stress_floor"
