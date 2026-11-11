"""Alert provenance for story changes and trim candidates."""
from __future__ import annotations

from signals.alert_provenance import (
    build_trim_candidates_from_holdings,
    detect_story_change,
    trim_alert_meta,
)


def test_story_regime_flip():
    out = detect_story_change(
        {"regime": "UP", "composite_buy": 70},
        regime="NEUTRAL",
        composite_buy=68,
        current_row={},
    )
    assert out is not None
    assert out["story_change_trigger"] == "regime_flip"
    assert out["story_change_source"] == "composite"
    assert "UP" in out["story_change"]


def test_story_ma50_reclaim():
    out = detect_story_change(
        {"regime": "DOWN", "composite_buy": 40, "close": 95.0, "ma50": 100.0},
        regime="DOWN",
        composite_buy=42,
        current_row={"close": 101.0, "ma50": 100.0},
    )
    assert out is not None
    assert out["story_change_trigger"] == "ma50_reclaim"
    assert "MA50 RECLAIM" in out["story_change"]


def test_story_ma50_reclaim_does_not_fire_every_day_above():
    """Already above MA50 both days -> no reclaim event (must be an actual crossing)."""
    out = detect_story_change(
        {"regime": "UP", "composite_buy": 70, "close": 105.0, "ma50": 100.0},
        regime="UP",
        composite_buy=70,
        current_row={"close": 106.0, "ma50": 100.0},
    )
    assert out is None


def test_story_momentum_extended_breakdown():
    out = detect_story_change(
        {
            "regime": "UP",
            "composite_buy": 80,
            "close": 148.0,
            "ma50": 140.0,
            "high_52w": 150.0,
        },
        regime="UP",
        composite_buy=78,
        current_row={"close": 138.0, "ma50": 140.0},
    )
    assert out is not None
    assert out["story_change_trigger"] == "momentum_extended_breakdown"
    assert "PULLBACK FROM HIGHS" in out["story_change"]


def test_story_regime_flip_takes_priority_over_ma50_transition():
    out = detect_story_change(
        {"regime": "UP", "composite_buy": 70, "close": 95.0, "ma50": 100.0},
        regime="NEUTRAL",
        composite_buy=70,
        current_row={"close": 101.0, "ma50": 100.0},
    )
    assert out is not None
    assert out["story_change_trigger"] == "regime_flip"


def test_story_no_ma50_transition_without_price_fields():
    out = detect_story_change(
        {"regime": "DOWN", "composite_buy": 40},
        regime="DOWN",
        composite_buy=42,
        current_row={},
    )
    assert out is None


def test_story_horizon_flip_only():
    out = detect_story_change(
        {"short_suggestion": "HOLD/ADD", "medium_suggestion": "HOLD", "long_suggestion": "HOLD"},
        regime="UP",
        composite_buy=70,
        current_row={
            "short_suggestion": "CONSIDER TRIM",
            "medium_suggestion": "HOLD",
            "long_suggestion": "HOLD",
        },
    )
    assert out is not None
    assert out["story_change_source"] == "horizon"
    assert out["story_change_horizon_flips"] == ["short"]


def test_trim_avoid_alone_is_hold_no_add():
    meta = trim_alert_meta(
        {
            "ticker": "MSFT",
            "score": 32,
            "action": "AVOID",
            "suggestion": "CONSIDER TRIM",
            "trim_gates_passed": 3,
            "trim_gates_total": 4,
            "trim_gate_cleared": True,
        },
        sell_max=35,
        trim_cfg={"enabled": True, "min_pass": 2},
    )
    assert not meta["is_trim_candidate"]
    assert meta["trim_recommendation"] == "hold_no_add"


def test_trim_plan_reduce_and_score():
    meta = trim_alert_meta(
        {
            "ticker": "MSFT",
            "score": 32,
            "action": "REDUCE",
            "suggestion": "CONSIDER TRIM",
            "trim_gates_passed": 3,
            "trim_gates_total": 4,
            "trim_gate_cleared": True,
        },
        sell_max=35,
        trim_cfg={"enabled": True, "min_pass": 2},
    )
    assert meta["is_trim_candidate"]
    assert meta["trim_source"] == "composite+plan"
    assert "plan_action" in meta["trim_triggers"]
    assert meta["trim_recommendation"] == "consider_trim"
    assert meta["trim_risk_reasons"] == ["plan_reduce"]


def test_trim_cached_avoid_plan_gate_is_rescored():
    gates = [
        {"id": "extension", "pass": False},
        {"id": "tape", "pass": True},
        {"id": "ml_momentum", "pass": False},
        {"id": "plan", "pass": True},
    ]
    meta = trim_alert_meta(
        {"ticker": "X", "score": 20, "action": "AVOID", "trim_gates": gates},
        sell_max=35,
        trim_cfg={"enabled": True, "min_pass": 2},
    )
    assert not meta["is_trim_candidate"]
    assert meta["trim_gates_passed"] == 1


def test_build_trim_candidates_sorted():
    extended = [
        {"id": "extension", "pass": True},
        {"id": "tape", "pass": True},
        {"id": "ml_momentum", "pass": True},
        {"id": "plan", "pass": False},
    ]
    rows = build_trim_candidates_from_holdings(
        [
            {"ticker": "A", "score": 50, "action": "HOLD", "suggestion": "HOLD"},
            {"ticker": "B", "score": 30, "action": "AVOID", "suggestion": "CONSIDER TRIM", "trim_gates": extended},
            {"ticker": "C", "score": 20, "action": "AVOID", "suggestion": "CONSIDER TRIM", "trim_gates_passed": 3, "trim_gate_cleared": True},
        ],
        sell_max=35,
        trim_cfg={"enabled": True, "min_pass": 2},
    )
    assert [r["ticker"] for r in rows] == ["B"]
    assert rows[0]["trim_primary_driver"]
    assert rows[0]["trim_risk_reasons"] == ["extended"]


def test_trim_below_owner_stop():
    base = {"ticker": "X", "score": 20, "action": "AVOID", "price": 90.0, "trim_gates_passed": 2, "trim_gate_cleared": True}
    meta = trim_alert_meta({**base, "owner_stop": 95.0}, sell_max=35, trim_cfg={"enabled": True, "min_pass": 2})
    assert meta["is_trim_candidate"]
    assert meta["trim_risk_reasons"] == ["stop_broken"]
    held = trim_alert_meta({**base, "owner_stop": 80.0, "swing_stop": 95.0}, sell_max=35, trim_cfg={"enabled": True, "min_pass": 2})
    assert not held["is_trim_candidate"]
