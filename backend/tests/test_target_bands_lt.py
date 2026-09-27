"""
LT band construction from the shared fair-value pipeline (signals/fair_value_pipeline.py).

Previously target_bands.py computed the long-term band from an independent PE-blend
(eps_fwd x fair_pe_low/high + analyst consensus) that could disagree by 20%+ with the real
model fair value used elsewhere in the app (see api/ticker_detail.py, retail_action_payload
valuation gate). This suite locks in the new behavior: the LT band, its midpoint (the
valuation gate's input), and its bear/base/bull scenarios are all derived from
row["fair_value"] — there is exactly one fair-value number driving all of it now.

No coverage existed for target_bands.py's LT section before this change.
"""
from __future__ import annotations

from signals.target_bands import LT_BULL_MULTIPLIER, add_target_bands


def _base_row(**overrides):
    row = {
        "ticker": "TEST",
        "close": 100.0,
        "atr14": 2.0,
        "ma20": 100.0,
        "regime": "NEUTRAL",
        "vol_6m": 0.25,
        "short_suggestion": "HOLD",
        "swing_high_20d": None,
        "swing_low_20d": None,
    }
    row.update(overrides)
    return row


def test_lt_fair_value_mid_is_the_point_estimate_directly():
    """This is the line that actually fixes the valuation-gate contradiction: lt_fair_value_mid
    must equal fair_value, not an average of some derived low/high range. Spot set equal to
    fair_value (fairly-valued case) so the display-width cap — a pre-existing, spot-relative
    cap unrelated to this change — doesn't trim the band and mask the raw multiplier math."""
    row = add_target_bands(_base_row(close=150.0, fair_value=150.0))
    assert row["lt_fair_value_mid"] == 150.0
    assert row["lt_band"] is not None
    assert row["lt_band"]["low"] < 150.0 < row["lt_band"]["high"]


def test_lt_band_uses_synthetic_bear_case_when_none_supplied():
    """No fair_value_bear_case from the pipeline -> synthetic 0.75x floor, and the bull leg
    uses the documented LT_BULL_MULTIPLIER default. Spot == fair_value for the same reason
    as above: the multiplier spread is sized to exactly match the display cap at that ratio."""
    row = add_target_bands(_base_row(close=200.0, fair_value=200.0))
    bear, bull = 200.0 * 0.75, 200.0 * LT_BULL_MULTIPLIER
    assert row["lt_scenarios"]["bear"] == round(bear, 2)
    assert row["lt_scenarios"]["bull"] == round(bull, 2)
    # "base" is the bear/bull midpoint (display scenario), not the fair-value point estimate
    # itself — that's lt_fair_value_mid, asserted separately above.
    assert row["lt_scenarios"]["base"] == round((bear + bull) / 2, 2)
    assert row["lt_fair_value_mid"] == 200.0


def test_lt_band_prefers_pipeline_bear_case_when_present():
    """When the estimator supplied its own bear_case (e.g. SPY earnings-yield or suppressed
    paths both set one), use it instead of the synthetic 0.75x floor."""
    row = add_target_bands(_base_row(fair_value=200.0, fair_value_bear_case=160.0))
    assert row["lt_scenarios"]["bear"] == 160.0


def test_lt_band_low_confidence_set_when_fair_value_suppressed():
    """Repurposed flag: previously meant 'analyst consensus is dispersed', now means 'the
    fair-value pipeline suppressed a real model estimate and street-anchored instead'."""
    row = add_target_bands(_base_row(fair_value=180.0, fair_value_suppressed=True))
    assert row["lt_band_low_confidence"] is True


def test_lt_band_falls_back_to_mt_scaled_when_fair_value_missing():
    """No fair_value at all (pipeline failure, or a caller like backtest_targets.py that never
    populates it) -> existing MT-band-scaled fallback, unchanged behavior."""
    row = add_target_bands(_base_row(short_suggestion="BUY", close=105.0, ma20=100.0))
    assert row.get("fair_value") is None
    assert row["lt_band"] is not None
    assert row["lt_band_low_confidence"] is True
    mt = row["mt_band"]
    assert row["lt_band"]["low"] <= mt["low"]
    assert row["lt_band"]["high"] >= mt["high"] or row.get("lt_band_width_capped")


def test_lt_band_falls_back_when_fair_value_is_zero_or_negative():
    """A suppressed pipeline result with no street anchor returns fair_value=None upstream
    (see fair_value_pipeline.py), but guard target_bands.py itself against a stray 0/negative
    value reaching it — must not build a band around $0."""
    row = add_target_bands(_base_row(fair_value=0.0))
    assert row["lt_band"] is not None
    assert row["lt_band"]["low"] > 0
    assert row["lt_band_low_confidence"] is True


def test_deeply_undervalued_name_can_hit_the_preexisting_display_cap():
    """Characterization, not a new behavior: _cap_band_width_for_display's 35%-of-SPOT cap is
    pre-existing (unchanged by this refactor) and is spot-relative while the fv-derived spread
    is fv-relative. For a name trading far below fair value, the capped displayed band's high
    can end up below fair_value itself — true of the old PE-blend LT model too (same cap
    function, same interaction), not a regression introduced by anchoring on fair_value."""
    row = add_target_bands(_base_row(close=100.0, fair_value=150.0))  # 50% below fair value
    assert row.get("lt_band_width_capped") is True
    assert row["lt_fair_value_mid"] == 150.0  # gate input is unaffected by display capping


def test_lt_band_contains_fair_value_even_with_bear_case_above_it():
    """Defensive: if a caller ever supplies a bear_case >= fair_value (shouldn't happen from
    the real pipeline, but the band-building code must not silently produce an inverted or
    fair-value-excluding range)."""
    row = add_target_bands(_base_row(fair_value=100.0, fair_value_bear_case=110.0))
    assert row["lt_band"]["low"] <= 100.0 <= row["lt_band"]["high"]
