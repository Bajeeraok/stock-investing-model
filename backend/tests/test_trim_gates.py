"""Trim gate stack (hybrid v1: B structure, min_pass=2)."""
from __future__ import annotations

from signals.alert_provenance import trim_alert_meta
from signals.trim_gates import (
    attach_trim_gates_to_row,
    build_trim_gates,
    evaluate_trim_recommendation,
    score_trim_triggered,
)


def test_score_trim_triggered():
    assert score_trim_triggered({"composite_buy": 25}, sell_max=30)
    assert not score_trim_triggered({"composite_buy": 55}, sell_max=30)
    assert score_trim_triggered({"short_suggestion": "CONSIDER TRIM"}, sell_max=30)


def test_build_trim_gates_extension_and_tape():
    gates = build_trim_gates(
        current_price=100,
        assessment_pct=-8,
        regime_bull_pct=38,
        pattern_score=35,
        short_ml_prob=0.25,
        rsi=72,
        macd_hist=-0.5,
        regime="DOWN",
        plan_action="REDUCE",
    )
    passed = sum(1 for g in gates if g["pass"])
    assert passed >= 3
    ids = {g["id"] for g in gates if g["pass"]}
    assert "extension" in ids
    assert "tape" in ids


def test_evaluate_trim_requires_gates_when_enabled():
    gates = build_trim_gates(
        current_price=100,
        assessment_pct=10,
        regime_bull_pct=70,
        pattern_score=60,
        short_ml_prob=0.6,
        rsi=45,
        macd_hist=0.2,
        regime="UP",
        plan_action="HOLD",
    )
    row = {"composite_buy": 28}
    summary = evaluate_trim_recommendation(row, gates, sell_max=30, cfg={"enabled": True, "min_pass": 2})
    assert summary["trim_score_triggered"]
    assert not summary["trim_gate_cleared"]


def test_attach_trim_gates_to_row():
    row = {
        "ticker": "TEST",
        "close": 100,
        "composite_buy": 25,
        "rsi": 70,
        "regime": "DOWN",
        "regime_bull_pct": 40,
        "ml_short_prob": 0.2,
        "macd_hist": -0.1,
        "plan_action": "REDUCE",
        "lt_band": {"low": 95, "high": 105},
        "retail_status": {},
    }
    attach_trim_gates_to_row(row, sell_max=30, config={"trim_gates": {"enabled": True, "min_pass": 2}})
    assert row.get("trim_gates_passed", 0) >= 2
    assert row.get("trim_score_triggered")


def test_trim_alert_meta_gated():
    meta = trim_alert_meta(
        {
            "ticker": "X",
            "score": 28,
            "action": "AVOID",
            "suggestion": "CONSIDER TRIM",
            "trim_gates_passed": 3,
            "trim_gates_total": 4,
            "trim_gate_cleared": True,
        },
        sell_max=30,
        trim_cfg={"enabled": True, "min_pass": 2},
    )
    assert meta["is_trim_candidate"]
    assert meta["trim_gate_cleared"]

    blocked = trim_alert_meta(
        {"ticker": "Y", "score": 28, "trim_gates_passed": 1, "trim_gate_cleared": False},
        sell_max=30,
        trim_cfg={"enabled": True, "min_pass": 2},
    )
    assert not blocked["is_trim_candidate"]
    assert blocked.get("trim_gates_pending")
