"""
Owner-mode House panel vs. overall verdict "conflict" — reported as a contradiction:
the header showed DOWN / low meta-confidence while the House panel said "entry
justified, full size OK" with no qualifier. Both readings are legitimately correct
(cheap valuation + weak regime is a real state), but the label didn't say so. Fix:
when valuation alone (assess_verdict) says BUY/PARTIAL but this horizon's own overall
verdict lands lower, append a caveat to the assessment label instead of leaving it as
an unqualified green light.
"""
from __future__ import annotations

from signals.horizon_entry_calculator import LongTermInputs, compute_long_term_entry


def _long_inputs(**overrides) -> LongTermInputs:
    base = dict(
        current_price=100.0,
        fair_value=200.0,
        ma200=180.0,
        week52_low=70.0,
        ml_prob=45.0,
        regime_bull_pct=55.0,
        fundamentals_score=72.0,
        ticker="TEST",
        tier2_mos_pct=15.0,
        medium_entry_high=105.0,
    )
    base.update(overrides)
    return LongTermInputs(**base)


def test_caveat_added_when_valuation_says_buy_but_regime_blocks_overall_verdict():
    """GOOGL-style: deep MOS discount (BUY on valuation) but weak regime -> overall verdict
    is not BUY. The label must say the BUY is valuation-only, not an unqualified green light."""
    sig = compute_long_term_entry(
        _long_inputs(current_price=65.0, fair_value=200.0, regime_bull_pct=0.0, ml_prob=10.0)
    )
    ca = sig.entry_tiers["current_assessment"]
    assert ca["verdict"] == "BUY"  # valuation-only assessment
    assert sig.verdict != "BUY"  # overall horizon verdict did not confirm
    assert "valuation only" in ca["label"].lower()
    assert sig.verdict in ca["label"]


def test_no_caveat_when_overall_verdict_agrees():
    """Regime/ML confirm too -> overall verdict is BUY, matching valuation. No caveat needed;
    the label must not be altered."""
    sig = compute_long_term_entry(
        _long_inputs(current_price=65.0, fair_value=200.0, regime_bull_pct=80.0, ml_prob=60.0)
    )
    ca = sig.entry_tiers["current_assessment"]
    assert ca["verdict"] == "BUY"
    assert sig.verdict == "BUY"
    assert "valuation only" not in ca["label"].lower()


def test_no_caveat_when_valuation_itself_says_wait():
    """Valuation says WAIT (insufficient MOS) -> nothing to caveat; label stays as-is regardless
    of the overall verdict."""
    sig = compute_long_term_entry(
        _long_inputs(current_price=195.0, fair_value=200.0, regime_bull_pct=0.0, ml_prob=10.0)
    )
    ca = sig.entry_tiers["current_assessment"]
    assert ca["verdict"] == "WAIT"
    assert "valuation only" not in ca["label"].lower()
