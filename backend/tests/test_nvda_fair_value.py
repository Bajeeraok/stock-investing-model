"""NVDA-class high-growth fair value — growth cap + street blend."""
from __future__ import annotations

from signals.fair_value_estimator import estimate_fair_value


def test_nvda_growth_capped_and_disclosed():
    r = estimate_fair_value(
        current_price=180.0,
        ttm_pe=55.0,
        sector_pe=28.0,
        revenue_growth_pct=122.0,
        earnings_growth_pct=145.0,
        net_margin_pct=55.0,
        de_ratio=0.41,
        forward_pe=28.0,
        sector_forward_pe=25.0,
        analyst_target=309.0,
    )
    assert r.growth_was_capped is True
    assert r.growth_raw_pct == 145.0
    assert r.growth_used_pct == 65.0
    assert any("capped" in n.lower() for n in r.notes)
    assert "forward_pe_blend" in r.method_used


def test_nvda_street_blend_when_model_far_below_street():
    r = estimate_fair_value(
        current_price=180.0,
        ttm_pe=55.0,
        sector_pe=28.0,
        revenue_growth_pct=122.0,
        earnings_growth_pct=145.0,
        net_margin_pct=55.0,
        de_ratio=0.41,
        forward_pe=28.0,
        sector_forward_pe=25.0,
        analyst_target=309.0,
    )
    # After 65% cap + street blend, FV should be materially closer to street than raw ~199
    assert r.fair_value >= 309.0 * 0.72
    assert r.fair_value <= 309.0 * 1.10
    assert any("blended" in n.lower() or "below street" in n.lower() for n in r.notes)


def test_high_growth_forward_missing_uses_analyst_floor_not_ttm_peg():
    r = estimate_fair_value(
        current_price=180.0,
        ttm_pe=55.0,
        sector_pe=28.0,
        revenue_growth_pct=122.0,
        earnings_growth_pct=145.0,
        net_margin_pct=55.0,
        de_ratio=0.41,
        forward_pe=None,
        sector_forward_pe=None,
        analyst_target=309.0,
    )
    assert r.fair_value >= 309.0 * 0.72
    assert "analyst_floor" in r.method_used or "peg_blend_fallback" not in r.method_used
