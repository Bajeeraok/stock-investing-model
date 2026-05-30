"""Tests for historical gate backtest helpers."""
from __future__ import annotations

from signals.gate_backtest import (
    evaluate_gates_at_point,
    enrich_row_with_gates,
    summarize_gate_backtest,
    cohort_forward_stats,
)


def test_evaluate_gates_all_pass():
    out = evaluate_gates_at_point(
        assessment_pct=12.0,
        regime_bull_pct=70.0,
        pattern_score=60.0,
        short_ml_prob=40.0,
        rsi=42.0,
    )
    assert out["gates_passed"] == 4
    assert out["gate_cleared"] is True
    assert out["go_no_go"] == "go"
    assert out["valuation_pass"] is True
    assert out["ml_pass"] is True


def test_evaluate_gates_regime_blocks():
    out = evaluate_gates_at_point(
        assessment_pct=10.0,
        regime_bull_pct=35.0,
        pattern_score=60.0,
        short_ml_prob=50.0,
        rsi=40.0,
    )
    assert out["regime_pass"] is False
    assert out["gate_cleared"] is False


def test_enrich_row_with_gates():
    row = {"ticker": "SPY", "date": "2024-01-15", "composite_buy": 72.0, "fwd_21d_pct": 3.5}
    sig = {"composite_buy": 72.0, "confluence_score": 68.0, "suggested_buy_price": 95.0}
    enrich_row_with_gates(
        row,
        close=100.0,
        sig=sig,
        regime_bull_pct=65.0,
        rsi=44.0,
        predict_ml=False,
    )
    assert "gates_passed" in row
    assert row.get("fwd_21d_pct") == 3.5


def test_summarize_gate_cohorts():
    rows = [
        {
            "composite_buy": 75,
            "gates_passed": 4,
            "gate_cleared": True,
            "go_no_go": "go",
            "fwd_21d_pct": 5.0,
            "valuation_pass": True,
            "regime_pass": True,
            "momentum_pass": True,
            "ml_pass": True,
        },
        {
            "composite_buy": 75,
            "gates_passed": 2,
            "gate_cleared": False,
            "go_no_go": "no_go",
            "fwd_21d_pct": -2.0,
            "valuation_pass": True,
            "regime_pass": False,
            "momentum_pass": True,
            "ml_pass": False,
        },
        {
            "composite_buy": 50,
            "gates_passed": 4,
            "gate_cleared": True,
            "fwd_21d_pct": 1.0,
            "valuation_pass": True,
            "regime_pass": True,
            "momentum_pass": True,
            "ml_pass": True,
        },
    ]
    s = summarize_gate_backtest(rows, horizons=(21,), buy_min=70.0, min_gates_passed=4)
    h21 = s["by_horizon_trading_days"]["21"]
    assert h21["gate_cleared_4of4"]["n"] == 2
    assert h21["gate_cleared_4of4"]["mean_fwd_pct"] == 3.0
    assert h21["composite_ge_buy_min"]["n"] == 2
    assert h21["composite_and_gate_cleared"]["n"] == 1
    assert h21["composite_and_gate_cleared"]["mean_fwd_pct"] == 5.0


def test_cohort_forward_stats():
    rows = [{"fwd_63d_pct": 4.0}, {"fwd_63d_pct": -1.0}]
    st = cohort_forward_stats(rows, "fwd_63d_pct")
    assert st["n"] == 2
    assert st["mean_fwd_pct"] == 1.5
    assert st["hit_rate_pct"] == 50.0
