"""Config-driven fair value guardrails (forecast-accuracy research vs retail caps)."""
from __future__ import annotations

from signals.fair_value_estimator import _apply_fair_value_guardrails, estimate_fair_value


def test_guardrails_default_caps_vs_analyst_and_spot():
    fv = 200.0
    price = 100.0
    analyst = 120.0
    out, notes = _apply_fair_value_guardrails(fv, price, analyst, None)
    # analyst cap: 120 * 1.1 = 132
    assert out == 132.0
    assert any("analyst" in n.lower() for n in notes)


def test_guardrails_disable_analyst_cap():
    fv = 200.0
    price = 100.0
    analyst = 120.0
    out, notes = _apply_fair_value_guardrails(
        fv, price, analyst, {"analyst_mean_cap_enabled": False, "max_implied_upside_vs_spot": 0.52}
    )
    # spot cap: 100 * 1.52 = 152
    assert out == 152.0
    assert not any("analyst" in n.lower() and "capped" in n.lower() for n in notes)


def test_guardrails_disable_spot_cap():
    fv = 200.0
    price = 100.0
    out, notes = _apply_fair_value_guardrails(
        fv, price, None, {"analyst_mean_cap_enabled": False, "max_implied_upside_vs_spot": None}
    )
    assert out == 200.0
    assert notes == []


def test_estimate_fair_value_accepts_guardrails_kwarg():
    r = estimate_fair_value(
        current_price=100.0,
        ttm_pe=20.0,
        sector_pe=22.0,
        revenue_growth_pct=8.0,
        earnings_growth_pct=8.0,
        net_margin_pct=15.0,
        de_ratio=0.5,
        analyst_target=105.0,
        guardrails={"analyst_mean_cap_enabled": False, "max_implied_upside_vs_spot": None},
    )
    assert r.fair_value > 100.0
