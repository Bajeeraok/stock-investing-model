"""
signals/fair_value_estimator.py's bear-case derivation. Regression for the reported
inconsistency: the main estimate_fair_value() path used a flat FV x 0.60 haircut while
every other path in the fair-value pipeline (suppressed names, negative-EPS street
anchor, extreme-divergence guardrail) already used FV x 0.75 — three different flat
percentages, none derived from anything real. Fixed by deriving a genuine "earnings
down + multiple compression" bear case from EPS/PE when those inputs are clean, falling
back to a single consistent flat multiplier (matching the rest of the pipeline) otherwise.
"""
from __future__ import annotations

from signals.fair_value_estimator import (
    _BEAR_CASE_FALLBACK_MULT,
    _BEAR_EPS_HAIRCUT_PCT,
    _BEAR_PE_COMPRESSION_PCT,
    _bear_case,
    estimate_fair_value,
)


class TestBearCaseHelper:
    def test_derives_from_eps_and_pe_when_both_available(self):
        bear, label = _bear_case(fv=200.0, ttm_pe=30.0, sector_pe=28.0, current_eps=5.0)
        expected_bear_eps = 5.0 * (1 - _BEAR_EPS_HAIRCUT_PCT)
        expected_bear_pe = 28.0 * _BEAR_PE_COMPRESSION_PCT  # sector_pe is lower of the two
        expected = round(expected_bear_eps * expected_bear_pe, 2)
        assert bear == expected
        assert "bear EPS" in label

    def test_uses_lower_of_ttm_and_sector_pe(self):
        bear_sector_lower, _ = _bear_case(fv=200.0, ttm_pe=40.0, sector_pe=25.0, current_eps=5.0)
        bear_ttm_lower, _ = _bear_case(fv=200.0, ttm_pe=20.0, sector_pe=25.0, current_eps=5.0)
        assert bear_sector_lower == round(5.0 * 0.8 * 25.0 * 0.7, 2)
        assert bear_ttm_lower == round(5.0 * 0.8 * 20.0 * 0.7, 2)

    def test_falls_back_to_flat_multiplier_without_eps(self):
        bear, label = _bear_case(fv=200.0, ttm_pe=30.0, sector_pe=28.0, current_eps=None)
        assert bear == round(200.0 * _BEAR_CASE_FALLBACK_MULT, 2)
        assert "unavailable" in label

    def test_falls_back_to_flat_multiplier_without_ttm_pe(self):
        bear, _ = _bear_case(fv=200.0, ttm_pe=None, sector_pe=28.0, current_eps=5.0)
        assert bear == round(200.0 * _BEAR_CASE_FALLBACK_MULT, 2)

    def test_falls_back_when_derived_bear_exceeds_fair_value(self):
        """A pathological input (e.g. absurdly high EPS/PE) must not produce a 'bear case'
        that's actually above fair value — fall back to the flat cut instead."""
        bear, label = _bear_case(fv=50.0, ttm_pe=100.0, sector_pe=100.0, current_eps=10.0)
        assert bear == round(50.0 * _BEAR_CASE_FALLBACK_MULT, 2)
        assert "unavailable" in label

    def test_none_when_fair_value_non_positive(self):
        bear, _ = _bear_case(fv=0.0, ttm_pe=30.0, sector_pe=28.0, current_eps=5.0)
        assert bear is None


class TestEstimateFairValueUsesBearCaseHelper:
    def test_bear_case_no_longer_hardcoded_at_point_six(self):
        """The main path's methodology_summary must reflect the new derivation, not the old
        flat 'FV×0.6' label."""
        r = estimate_fair_value(
            current_price=100.0, ttm_pe=20.0, sector_pe=22.0,
            revenue_growth_pct=8.0, earnings_growth_pct=8.0,
            net_margin_pct=15.0, de_ratio=0.5, current_eps=5.0,
        )
        assert r.bear_case is not None
        assert r.bear_case != round(r.fair_value * 0.60, 2)
        assert "FV×0.6" not in (r.methodology_summary or "")

    def test_bear_case_still_populated_without_current_eps(self):
        """Callers that don't pass current_eps (there are several) must still get a sane,
        consistent bear case via the flat-multiplier fallback, not a crash or None."""
        r = estimate_fair_value(
            current_price=100.0, ttm_pe=20.0, sector_pe=22.0,
            revenue_growth_pct=8.0, earnings_growth_pct=8.0,
            net_margin_pct=15.0, de_ratio=0.5,
        )
        assert r.bear_case is not None
        assert r.bear_case == round(r.fair_value * _BEAR_CASE_FALLBACK_MULT, 2)
