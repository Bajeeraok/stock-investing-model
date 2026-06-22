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
    """Spot well below FV → MOS BUY and within full-size ceiling."""
    sig = compute_long_term_entry(_long_inputs(current_price=100.0, fair_value=200.0))
    ca = sig.entry_tiers["current_assessment"]
    assert ca["min_price_to_buy"] == 150.0  # 25% MOS to FV
    assert ca["within_full_mos_ceiling"] is True
    assert ca.get("above_full_mos_ceiling") is not True
    assert ca["full_size_eligible_at_spot"] is True
    assert ca["verdict"] == "BUY"


def test_below_all_tiers_but_within_mos_ceiling():
    """Crash below MA200 tiers but still under full-size ceiling — no chase-wait contradiction."""
    sig = compute_long_term_entry(
        _long_inputs(
            current_price=120.0,
            fair_value=200.0,
            ma200=180.0,
            week52_low=70.0,
        )
    )
    sp = sig.entry_tiers["spot_position"]
    ca = sig.entry_tiers["current_assessment"]
    assert ca["within_full_mos_ceiling"] is True
    assert ca["full_size_eligible_at_spot"] is True
    assert sp.get("below_all_within_mos") is True
    assert sp.get("state") == "below_all"
    assert "full-size ceiling" in (sp.get("detail") or "").lower()
    assert "full-size ceiling" in sig.trigger_buy.lower() or "full mos" in sig.trigger_buy.lower()


def test_spot_above_ceiling_not_eligible():
    sig = compute_long_term_entry(_long_inputs(current_price=160.0, fair_value=200.0))
    ca = sig.entry_tiers["current_assessment"]
    assert ca["min_price_to_buy"] == 150.0
    assert ca.get("within_full_mos_ceiling") is not True
    assert ca.get("full_size_eligible_at_spot") is not True
