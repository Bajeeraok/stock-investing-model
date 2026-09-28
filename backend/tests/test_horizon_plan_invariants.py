"""Horizon plan-quality invariants: forward FV, monotonic targets, entry R:R, extended mode."""

from __future__ import annotations

from signals.horizon_entry_calculator import (
    LT_FORWARD_GROWTH_CAP_PCT,
    PLAN_MIN_RR_FROM_ENTRY,
    _apply_horizon_plan_invariants,
    _forward_fair_value,
    _plausibility_cap,
    _rr_from_entry_mid,
    build_all_horizons_payload,
)


def test_forward_fair_value_grows_with_eps():
    assert _forward_fair_value(500.0, 10.0, years=1.0) == 550.0


class TestForwardFairValueGrowthCap:
    """Regression: fair_value_estimator's peg_blend/forward_pe methods already price growth
    INTO fv — growing that already-growth-priced number by the model's own growth rate again
    for the 1-year forward-lift double-counts it. Confirmed live: GOOGL's fv ($474.73, from a
    42%-growth peg_blend) got lifted by another 40% to a $664.62 forward FV. The lift's own
    growth input is capped independently and much tighter than fair_value_estimator's cap."""

    def test_high_growth_input_is_capped_at_the_lift_specific_ceiling(self):
        # GOOGL-style: fv already priced with 42% growth; lift must use the capped 15%, not 42%.
        fv = _forward_fair_value(474.73, 42.0, years=1.0)
        assert fv == round(474.73 * (1 + LT_FORWARD_GROWTH_CAP_PCT / 100.0), 2)
        assert fv < 474.73 * 1.40  # materially below the old 40%-cap behavior

    def test_very_high_growth_input_also_capped(self):
        # AMD-style: 65% growth input, same 15% ceiling applies.
        fv = _forward_fair_value(516.88, 65.0, years=1.0)
        assert fv == round(516.88 * (1 + LT_FORWARD_GROWTH_CAP_PCT / 100.0), 2)

    def test_low_growth_names_unaffected(self):
        # PG-style: 1.5% growth is well under the cap — no behavior change.
        fv = _forward_fair_value(173.56, 1.5, years=1.0)
        assert fv == round(173.56 * 1.015, 2)

    def test_default_growth_fallback_unaffected(self):
        # JPM-style: no growth data -> LT_DEFAULT_GROWTH_PCT (8%) fallback, under the cap.
        fv = _forward_fair_value(373.64, None, years=1.0)
        assert fv == round(373.64 * 1.08, 2)


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


class TestPlausibilityCap:
    """Regression: medium/long targets could compound (forward-FV lift + cross-horizon
    monotonicity) far past both realistic volatility and the published analyst high — the
    reported case was GOOGL showing a medium target of $619.82 (+80% in 3 months) and a
    long target of $664.62 (+93%) against an analyst high of $485."""

    def test_vol_cap_binds_when_tighter_than_analyst_cap(self):
        cap = _plausibility_cap(current_price=343.92, atr=7.0, analyst_high=485.0, trading_days=63)
        assert cap is not None
        assert cap < 485.0 * 1.15  # vol cap is the binding constraint here

    def test_analyst_cap_binds_when_tighter_than_vol_cap(self):
        cap = _plausibility_cap(current_price=343.92, atr=7.0, analyst_high=485.0, trading_days=252)
        assert cap is not None
        assert abs(cap - 485.0 * 1.15) < 0.01  # analyst cap is the binding constraint here

    def test_no_cap_when_neither_input_available(self):
        assert _plausibility_cap(current_price=343.92, atr=None, analyst_high=None, trading_days=63) is None

    def test_falls_back_to_whichever_input_is_available(self):
        vol_only = _plausibility_cap(current_price=100.0, atr=2.0, analyst_high=None, trading_days=63)
        assert vol_only is not None
        analyst_only = _plausibility_cap(current_price=100.0, atr=None, analyst_high=120.0, trading_days=63)
        assert analyst_only == 120.0 * 1.15

    def test_googl_style_targets_get_capped_down(self):
        """End-to-end through _apply_horizon_plan_invariants, mirroring the reported case."""
        payload = {
            "short": {
                "entry_zone": {"low": 335.0, "high": 344.0},
                "stop_loss": 320.0, "target": 360.0,
                "verdict": "WATCH", "warnings": [],
            },
            "medium": {
                "entry_zone": {"low": 333.82, "high": 347.58},
                "stop_loss": 323.49, "target": 619.82,
                "verdict": "WATCH", "warnings": [],
            },
            "long": {
                "entry_zone": {"low": 320.93, "high": 347.58},
                "stop_loss": 307.17, "target": 664.62,
                "verdict": "WAIT", "warnings": [], "fair_value": 474.73,
            },
        }
        _apply_horizon_plan_invariants(
            payload,
            current_price=343.92,
            fair_value=474.73,
            atr=7.0,
            earnings_growth_pct=12.0,
            analyst_target_high=485.0,
        )
        assert payload["medium"]["target"] < 619.82
        assert payload["long"]["target"] < 664.62
        assert payload["long"]["target"] <= 485.0 * 1.15 + 0.01
        assert any("capped" in w.lower() for w in payload["medium"]["warnings"])
        assert any("capped" in w.lower() for w in payload["long"]["warnings"])

    def test_no_analyst_high_still_caps_via_volatility_alone(self):
        payload = {
            "short": {"entry_zone": {"low": 335.0, "high": 344.0}, "stop_loss": 320.0, "target": 360.0,
                      "verdict": "WATCH", "warnings": []},
            "medium": {"entry_zone": {"low": 333.82, "high": 347.58}, "stop_loss": 323.49, "target": 619.82,
                       "verdict": "WATCH", "warnings": []},
            "long": {"entry_zone": {"low": 320.93, "high": 347.58}, "stop_loss": 307.17, "target": 664.62,
                     "verdict": "WAIT", "warnings": [], "fair_value": 474.73},
        }
        _apply_horizon_plan_invariants(
            payload, current_price=343.92, fair_value=474.73, atr=7.0,
            earnings_growth_pct=12.0, analyst_target_high=None,
        )
        assert payload["medium"]["target"] < 619.82
        assert payload["long"]["target"] < 664.62

    def test_reasonable_target_is_left_alone(self):
        """A target already inside plausible bounds must not be touched."""
        payload = {
            "short": {"entry_zone": {"low": 95.0, "high": 100.0}, "stop_loss": 90.0, "target": 108.0,
                      "verdict": "WATCH", "warnings": []},
            "medium": {"entry_zone": {"low": 95.0, "high": 100.0}, "stop_loss": 90.0, "target": 112.0,
                       "verdict": "WATCH", "warnings": []},
            "long": {"entry_zone": {"low": 90.0, "high": 100.0}, "stop_loss": 85.0, "target": 118.0,
                     "verdict": "WAIT", "warnings": [], "fair_value": 118.0},
        }
        _apply_horizon_plan_invariants(
            payload, current_price=100.0, fair_value=118.0, atr=2.0,
            earnings_growth_pct=8.0, analyst_target_high=130.0,
        )
        assert payload["medium"]["target"] == 112.0
        assert not any("capped" in w.lower() for w in payload["medium"]["warnings"])


class TestStreetDivergenceDisclosure:
    """A high-conviction model call that genuinely diverges from street consensus must stay
    visible, not get silently clamped to consensus — that would defeat the point of running
    a model at all. The gap gets surfaced as a note instead."""

    def _payload(self, long_target=545.94, medium_target=300.0):
        # fair_value=None in the payload's "long" entry AND passed to the invariants call
        # (below) disables the unrelated forward-FV lift (step 1) and extended-above-FV
        # check (step 4), so these tests exercise the street-divergence disclosure (step 2c)
        # in isolation against an explicitly-chosen target.
        return {
            # Short target kept well below both medium/long test values so the pre-existing
            # cross-horizon monotonicity step (2) never cascades and overwrites them.
            "short": {"entry_zone": {"low": 200.0, "high": 210.0}, "stop_loss": 190.0, "target": 220.0,
                      "verdict": "WATCH", "warnings": []},
            "medium": {"entry_zone": {"low": 333.82, "high": 347.58}, "stop_loss": 323.49,
                       "target": medium_target, "verdict": "WATCH", "warnings": []},
            "long": {"entry_zone": {"low": 320.93, "high": 347.58}, "stop_loss": 307.17,
                     "target": long_target, "verdict": "WAIT", "warnings": []},
        }

    def test_discloses_gap_without_changing_the_target(self):
        payload = self._payload(long_target=545.94)
        _apply_horizon_plan_invariants(
            payload, current_price=340.63, fair_value=None, atr=8.47,
            analyst_target_median=431.57,
        )
        assert payload["long"]["target"] == 545.94  # unchanged — no clamp
        assert any("street consensus" in w.lower() for w in payload["long"]["warnings"])
        assert any("+26" in w or "+27" in w for w in payload["long"]["warnings"])

    def test_no_note_when_within_threshold_of_street(self):
        payload = self._payload(long_target=460.0)  # ~6.6% vs 431.57 median — under threshold
        _apply_horizon_plan_invariants(
            payload, current_price=340.63, fair_value=None, atr=8.47,
            analyst_target_median=431.57,
        )
        assert not any("street consensus" in w.lower() for w in payload["long"]["warnings"])

    def test_no_note_when_median_unavailable(self):
        payload = self._payload(long_target=545.94)
        _apply_horizon_plan_invariants(
            payload, current_price=340.63, fair_value=None, atr=8.47,
            analyst_target_median=None,
        )
        assert not any("street consensus" in w.lower() for w in payload["long"]["warnings"])

    def test_negative_divergence_also_disclosed(self):
        """A target well BELOW street consensus is just as much a divergent call and should
        be disclosed too, not only upside divergence."""
        payload = self._payload(long_target=300.0, medium_target=290.0)  # ~-30% vs 431.57
        _apply_horizon_plan_invariants(
            payload, current_price=340.63, fair_value=None, atr=8.47,
            analyst_target_median=431.57,
        )
        assert any("street consensus" in w.lower() for w in payload["long"]["warnings"])
        assert any("-30" in w or "-31" in w or "-29" in w for w in payload["long"]["warnings"])


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
