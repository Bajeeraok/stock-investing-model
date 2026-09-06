"""PositionSizingEngine's position-size cap must follow the same risk-profile ladder
(15/20/25%) as portfolio/doctor.py's max_position_pct, instead of a hardcoded 10% that
silently disagreed with the user's selected profile — see
docs/signals/RETAIL_DATA_SURFACING.md."""

from __future__ import annotations

from signals.tier1_risk_engine import PositionSizingEngine, RiskTolerance


def test_cap_follows_risk_profile_ladder():
    conservative = PositionSizingEngine(100_000, risk_tolerance=RiskTolerance.CONSERVATIVE)
    moderate = PositionSizingEngine(100_000, risk_tolerance=RiskTolerance.MODERATE)
    aggressive = PositionSizingEngine(100_000, risk_tolerance=RiskTolerance.AGGRESSIVE)

    assert conservative.MAX_SINGLE_POSITION_PCT == 0.15
    assert moderate.MAX_SINGLE_POSITION_PCT == 0.20
    assert aggressive.MAX_SINGLE_POSITION_PCT == 0.25


def test_explicit_max_position_pct_overrides_ladder():
    eng = PositionSizingEngine(100_000, risk_tolerance=RiskTolerance.MODERATE, max_position_pct=0.33)
    assert eng.MAX_SINGLE_POSITION_PCT == 0.33


def test_default_construction_still_moderate_matches_doctor_ladder():
    """Default risk_tolerance (no explicit arg) should resolve to 20%, matching
    portfolio/doctor.py's moderate-profile cap — not the old hardcoded 10%."""
    eng = PositionSizingEngine(100_000)
    assert eng.MAX_SINGLE_POSITION_PCT == 0.20
