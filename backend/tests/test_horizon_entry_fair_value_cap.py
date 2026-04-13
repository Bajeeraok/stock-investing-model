"""Short-term entry band vs fair value — do not imply buying above intrinsic."""

from __future__ import annotations

from signals.horizon_entry_calculator import ShortTermInputs, compute_short_term_entry


def test_short_entry_capped_when_band_above_fair_value():
    """NVDA-style: spot/VWAP band above model FV must not stay as a 'buy' above intrinsic."""
    inp = ShortTermInputs(
        current_price=188.63,
        ml_prob=40.0,
        rsi=58.0,
        atr=6.0,
        vwap=187.0,
        support_level=175.0,
        resistance_level=205.0,
        regime_bull_pct=98.0,
        pattern_score=60.0,
        volume_ratio=1.0,
        fair_value=177.73,
    )
    sig = compute_short_term_entry(inp)
    ez = sig.entry_zone
    assert ez.high <= 178.0, f"entry high should cap at FV, got {ez.high}"
    assert ez.low < ez.high
    assert ez.low < 177.73


def test_short_entry_unchanged_when_band_already_below_fv():
    inp = ShortTermInputs(
        current_price=160.0,
        ml_prob=40.0,
        rsi=58.0,
        atr=5.0,
        vwap=158.0,
        support_level=150.0,
        resistance_level=175.0,
        regime_bull_pct=60.0,
        pattern_score=55.0,
        volume_ratio=1.0,
        fair_value=200.0,
    )
    sig = compute_short_term_entry(inp)
    ez = sig.entry_zone
    assert ez.high <= 200.0
    assert ez.high >= 158.0 * 0.98
