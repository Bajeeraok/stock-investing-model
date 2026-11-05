"""Full-size MOS ceiling vs structural tier bands when spot is below ceiling."""

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


def test_spot_below_ceiling_full_mos_eligible():
    """Spot well below FV and below all tier bands → MOS BUY and within full-size ceiling."""
    sig = compute_long_term_entry(_long_inputs(current_price=65.0, fair_value=200.0))
    ca = sig.entry_tiers["current_assessment"]
    assert ca["min_price_to_buy"] == 150.0  # 25% MOS to FV
    assert ca["within_full_mos_ceiling"] is True
    assert ca.get("above_full_mos_ceiling") is not True
    assert ca["full_size_eligible_at_spot"] is True
    assert ca["verdict"] == "BUY"


def test_below_all_tiers_but_within_mos_ceiling():
    """Crash below every tier band but still under full-size ceiling — tiers do not block full size."""
    sig = compute_long_term_entry(
        _long_inputs(
            current_price=65.0,
            fair_value=200.0,
            ma200=180.0,
            week52_low=70.0,
            medium_entry_high=None,
        )
    )
    sp = sig.entry_tiers["spot_position"]
    ca = sig.entry_tiers["current_assessment"]
    assert ca["within_full_mos_ceiling"] is True
    assert ca["full_size_eligible_at_spot"] is True
    assert sp.get("below_all_within_mos") is True
    # T1's ceiling check runs before the floor/ceiling-tier scan that used to produce a
    # dedicated "below_all" state, so a crash below every tier is classified as
    # "at_or_below_ceiling" (T1 is always the lowest-anchored tier) — the richer "full MOS
    # met at spot" framing is layered on top via below_all_within_mos regardless of which
    # of the two states got there. See horizon_entry_calculator.py::_enrich_mos_ceiling_context.
    assert sp.get("state") == "at_or_below_ceiling"
    assert "full-size ceiling" in (sp.get("detail") or "").lower()
    assert "full-size ceiling" in sig.trigger_buy.lower() or "full mos" in sig.trigger_buy.lower()


def test_spot_above_ceiling_not_eligible():
    sig = compute_long_term_entry(_long_inputs(current_price=160.0, fair_value=200.0))
    ca = sig.entry_tiers["current_assessment"]
    assert ca["min_price_to_buy"] == 150.0
    assert ca.get("within_full_mos_ceiling") is not True
    assert ca.get("full_size_eligible_at_spot") is not True


def test_mos_is_discount_to_fair_value_not_upside():
    """GS-like: 26% upside to FV is only a 21% discount — not the 25% MOS that min_price_to_buy requires."""
    sig = compute_long_term_entry(
        _long_inputs(current_price=868.0, fair_value=1097.5, ma200=950.67, week52_low=700.0, medium_entry_high=945.07)
    )
    ca = sig.entry_tiers["current_assessment"]
    assert ca["min_price_to_buy"] == 823.12
    assert ca["verdict"] != "BUY"
    assert ca["margin_of_safety_pct"] == 20.9


def test_tier2_stacks_under_tier1_when_both_capped_at_swing_top():
    sig = compute_long_term_entry(
        _long_inputs(current_price=868.0, fair_value=1097.5, ma200=950.67, week52_low=700.0, medium_entry_high=945.07)
    )
    t1, t2, t3 = sig.entry_tiers["tiers"]
    assert t1["high"] == 945.07
    assert t2["high"] <= t1["low"] + 0.01
    assert t3["high"] < t2["low"]
