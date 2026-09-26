"""Horizon plan-quality invariants: forward FV, monotonic targets, entry R:R, extended mode."""

from __future__ import annotations

from signals.horizon_entry_calculator import (
    PLAN_MIN_RR_FROM_ENTRY,
    _apply_horizon_plan_invariants,
    _forward_fair_value,
    _rr_from_entry_mid,
    build_all_horizons_payload,
)


def test_forward_fair_value_grows_with_eps():
    assert _forward_fair_value(500.0, 10.0, years=1.0) == 550.0


def test_rr_from_entry_mid_not_spot():
    # Spot-extended: from spot R:R looks terrible; from entry mid it's healthy.
    rr = _rr_from_entry_mid(entry_low=480, entry_high=500, stop=450, target=560)
    assert rr >= PLAN_MIN_RR_FROM_ENTRY


def test_apply_invariants_lifts_long_above_medium_and_marks_bad_short():
    payload = {
        "short": {
            "entry_zone": {"low": 500.0, "high": 514.0},
            "stop_loss": 460.0,
            "target": 535.0,  # ~0.6x from mid → no setup
            "verdict": "WATCH",
            "warnings": [],
        },
        "medium": {
            "entry_zone": {"low": 480.0, "high": 520.0},
            "stop_loss": 450.0,
            "target": 668.0,
            "verdict": "WATCH",
            "warnings": [],
        },
        "long": {
            "entry_zone": {"low": 380.0, "high": 420.0},
            "stop_loss": 350.0,
            "target": 514.0,  # shrinks vs medium — must lift
            "verdict": "WAIT",
            "warnings": [],
            "fair_value": 514.0,
        },
    }
    _apply_horizon_plan_invariants(
        payload,
        current_price=624.0,
        fair_value=514.0,
        atr=20.0,
        earnings_growth_pct=12.0,
    )
    assert payload["long"]["target"] >= payload["medium"]["target"] - 1e-6
    assert payload["long"].get("forward_fair_value") is not None
    assert payload["short"]["setup_status"] == "no_setup"
    assert payload["short"]["verdict"] == "WAIT"
    assert payload.get("plan_mode") == "pullback_conditional"
    assert payload.get("chase_banner") == "DO NOT CHASE"
    assert payload.get("fv_staleness", {}).get("flagged") is True


def test_build_all_horizons_payload_accepts_earnings_growth():
    """Smoke: new kwarg does not break payload build."""
    out = build_all_horizons_payload(
        current_price=100.0,
        rsi=45.0,
        atr=3.0,
        vwap=98.0,
        support_level=92.0,
        resistance_level=108.0,
        ma50=95.0,
        ma200=88.0,
        week52_low=70.0,
        volume_ratio=1.0,
        st_ml_prob=40.0,
        mt_ml_prob=45.0,
        lt_ml_prob=50.0,
        regime_bull_pct=55.0,
        pattern_score=60.0,
        fair_value=110.0,
        options_sentiment_score=50.0,
        insider_activity_score=50.0,
        fundamentals_score=60.0,
        ticker="TEST",
        earnings_growth_pct=10.0,
    )
    assert "short" in out and "medium" in out and "long" in out
    assert float(out["long"]["target"]) >= float(out["medium"]["target"]) - 1e-6
