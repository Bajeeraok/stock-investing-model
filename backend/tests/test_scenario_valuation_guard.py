"""Tests for valuation-aware scenario guards."""

from signals.scenario_valuation_guard import (
    apply_valuation_context_to_earnings_target,
    apply_valuation_guards_to_scenarios,
    premium_vs_fv_pct,
)


def test_nbis_like_overvalued_caps_earnings_beat():
    """Spot above street high + far above FV — earnings beat should not target $318 at 72%."""
    price = 286.69
    fv = 141.12
    scenarios = [
        {
            "scenario_type": "specific",
            "name": "Earnings Beat",
            "probability": 0.72,
            "price_target": 318.23,
            "return_pct": 11.0,
            "macro_note": None,
        },
        {
            "scenario_type": "bear",
            "name": "Bear Case",
            "probability": 0.05,
            "price_target": 170.0,
            "return_pct": -40.0,
        },
    ]
    analyst = {"high": 255.0, "median": 196.0, "low": 129.0}

    out, summary = apply_valuation_guards_to_scenarios(
        scenarios,
        price=price,
        fair_value=fv,
        analyst_targets=analyst,
    )

    beat = out[0]
    assert beat["price_target"] <= 268.0  # capped near analyst high + 5%
    assert beat["return_pct"] < 0  # still below spot
    assert beat["probability"] < 0.72
    assert beat.get("valuation_capped") is True
    assert summary.get("valuation_note")
    assert premium_vs_fv_pct(price, fv) > 90


def test_earnings_target_gets_tactical_note():
    et = {
        "available": True,
        "expected_move_pct": 10.1,
        "upside_target": 315.65,
        "downside_target": 257.73,
    }
    out = apply_valuation_context_to_earnings_target(
        et,
        price=286.69,
        fair_value=141.12,
        analyst_targets={"high": 255.0},
    )
    assert out.get("is_tactical_only") is True
    assert "1-day reaction band" in (out.get("valuation_context") or "")


def test_fairly_valued_no_cap():
    scenarios = [
        {
            "scenario_type": "specific",
            "name": "Earnings Beat",
            "probability": 0.45,
            "price_target": 110.0,
            "return_pct": 10.0,
        },
    ]
    out, summary = apply_valuation_guards_to_scenarios(
        scenarios,
        price=100.0,
        fair_value=95.0,
        analyst_targets={"high": 120.0, "median": 105.0},
    )
    assert out[0]["price_target"] == 110.0
    assert out[0]["probability"] == 0.45
    assert summary.get("valuation_note") is None
