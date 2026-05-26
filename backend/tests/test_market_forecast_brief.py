"""Market forecast brief must follow reconciled quadrant, not raw macro alone."""
from __future__ import annotations

from signals.market_forecast_brief import build_market_forecast_brief


def test_best_buy_zone_overrides_cautious_risk_off():
    brief = build_market_forecast_brief(
        {},
        macro_regime="Risk-Off",
        real_yield=2.2,
        vix=22.0,
        cross_asset=[],
        economic_calendar=[],
        market_context={
            "quadrant": "best_buy_zone",
            "primary_message": "FEAR IN A BULL MARKET",
            "explanation": "Best dip-buying setup historically.",
        },
        global_market_regime="STRONG_BULL",
    )
    assert brief is not None
    assert brief["bias"] == "constructive"
    assert "dip-buy" in brief["headline"].lower() or "selective" in brief["headline"].lower()
    assert "cautious — macro and volatility suggest defense" not in brief["headline"]
    assert not any(b.startswith("Unified read:") for b in brief["bullets"])


def test_reconciled_best_buy_no_duplicate_regime_bullets():
    brief = build_market_forecast_brief(
        {},
        macro_regime="Risk-Off",
        real_yield=2.2,
        vix=22.0,
        cross_asset=[],
        economic_calendar=[],
        market_context={
            "quadrant": "best_buy_zone",
            "primary_message": "FEAR IN A BULL MARKET",
            "explanation": "Best dip-buying setup historically.",
        },
        global_market_regime="STRONG_BULL",
    )
    assert brief is not None
    assert not any(b.startswith("Long-term SPY regime:") for b in brief["bullets"])
