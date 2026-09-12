"""Fed Rate Hike scenario — mirrors the existing Fed Rate Cut scenario for EQUITY_US,
gated on live CPI instead of fed funds level (see price_targets.py::_build_scenarios)."""

from __future__ import annotations

from signals.price_targets import _ASSET_SCENARIOS, _build_scenarios


def _names(scenarios: list[dict]) -> list[str]:
    return [s["name"] for s in scenarios]


def test_equity_us_has_four_asset_specific_scenarios_including_rate_hike():
    assert len(_ASSET_SCENARIOS["EQUITY_US"]) == 4
    names = [s["name"] for s in _ASSET_SCENARIOS["EQUITY_US"]]
    assert "Fed Rate Cut" in names
    assert "Fed Rate Hike" in names


def test_build_scenarios_surfaces_rate_hike_for_equity_us():
    scenarios = _build_scenarios(
        price=200.0,
        ml_prob_short=0.45,
        thr_short=10.0,
        asset_type="EQUITY_US",
        regime="NEUTRAL",
        vol_annual=0.25,
    )
    names = _names(scenarios)
    assert "Fed Rate Cut" in names
    assert "Fed Rate Hike" in names
    cut = next(s for s in scenarios if s["name"] == "Fed Rate Cut")
    hike = next(s for s in scenarios if s["name"] == "Fed Rate Hike")
    # Both scenarios apply a flat +/-5pp shift to the same base threshold return (thr_short),
    # not an independently-computed bearish/bullish target — so "Rate Hike" is only
    # guaranteed to score below "Rate Cut", not below zero, when thr_short is large.
    assert hike["return_pct"] < cut["return_pct"]
    assert 0.0 <= hike["probability"] <= 1.0


def test_rate_hike_probability_rises_with_hot_cpi():
    cool = _build_scenarios(
        price=200.0, ml_prob_short=0.45, thr_short=10.0,
        asset_type="EQUITY_US", regime="NEUTRAL", vol_annual=0.25,
        macro={"cpi_yoy": 2.0},
    )
    hot = _build_scenarios(
        price=200.0, ml_prob_short=0.45, thr_short=10.0,
        asset_type="EQUITY_US", regime="NEUTRAL", vol_annual=0.25,
        macro={"cpi_yoy": 4.2},
    )
    hike_cool = next(s for s in cool if s["name"] == "Fed Rate Hike")
    hike_hot = next(s for s in hot if s["name"] == "Fed Rate Hike")
    assert hike_hot["probability"] > hike_cool["probability"]
    assert "inflation still hot" in (hike_hot["trigger"] or "")
