"""Short-term target vs HMM: non-bull regimes cap tactical upside vs entry band high."""

from __future__ import annotations

from signals.horizon_entry_calculator import ShortTermInputs, compute_short_term_entry


def test_short_target_dampened_when_hmm_heavy_non_bull():
    """ATR×3 + resistance can imply ~7%+ vs eh; cap at 4% when bull prob is very low."""
    inp = ShortTermInputs(
        current_price=600.0,
        ml_prob=20.0,
        rsi=48.0,
        atr=15.0,
        vwap=595.0,
        support_level=580.0,
        resistance_level=700.0,
        regime_bull_pct=22.0,
        pattern_score=40.0,
        volume_ratio=1.0,
        fair_value=None,
    )
    sig = compute_short_term_entry(inp)
    eh = sig.entry_zone.high
    raw_pct = (sig.target - eh) / eh * 100.0
    assert raw_pct <= 4.05, f"expected <=4% upside vs eh in heavy non-bull, got {raw_pct:.2f}%"
    assert any("Short-term upside capped" in w for w in sig.warnings)


def test_short_target_unchanged_when_hmm_bullish_enough():
    inp = ShortTermInputs(
        current_price=600.0,
        ml_prob=40.0,
        rsi=48.0,
        atr=15.0,
        vwap=595.0,
        support_level=580.0,
        resistance_level=700.0,
        regime_bull_pct=55.0,
        pattern_score=60.0,
        volume_ratio=1.0,
        fair_value=None,
    )
    sig = compute_short_term_entry(inp)
    assert not any("Short-term upside capped" in w for w in sig.warnings)


def test_short_target_mild_cap_in_transition_regime():
    """[42, 48) bull uses 6.5% cap — ATR×3 would otherwise exceed it vs the entry band high."""
    inp = ShortTermInputs(
        current_price=600.0,
        ml_prob=30.0,
        rsi=48.0,
        atr=28.0,
        vwap=598.0,
        support_level=585.0,
        resistance_level=800.0,
        regime_bull_pct=44.0,
        pattern_score=45.0,
        volume_ratio=1.0,
        fair_value=None,
    )
    sig = compute_short_term_entry(inp)
    eh = sig.entry_zone.high
    pct = (sig.target - eh) / eh * 100.0
    assert pct <= 6.55, f"expected <=6.5% upside vs eh, got {pct:.2f}%"
    assert any("Short-term upside capped" in w for w in sig.warnings)
