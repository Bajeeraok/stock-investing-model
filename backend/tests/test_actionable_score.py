"""Tests for confidence-adjusted / actionable score."""
from __future__ import annotations

from signals.actionable_score import attach_actionable_score, compute_actionable_score


def test_mu_like_gates_and_confidence_discount():
    """Score 91 with 2/4 gates and 26% confidence → ~21 actionable."""
    out = compute_actionable_score(
        91.0,
        gates_passed=2,
        gates_total=4,
        fused_confidence_pct=26.0,
        confidence_target_pct=55.0,
    )
    assert out["setup_quality"] == 91.0
    assert out["actionable"] is not None
    # 91 * 0.5 * (26/55) ≈ 21.5
    assert 18.0 <= out["actionable"] <= 25.0
    assert out["factors"]["gate_multiplier"] == 0.5


def test_full_go_keeps_setup_near_raw():
    out = compute_actionable_score(
        80.0,
        gates_passed=4,
        gates_total=4,
        fused_confidence_pct=70.0,
    )
    assert out["actionable"] == 80.0


def test_stale_suppresses_headline():
    out = compute_actionable_score(
        91.0,
        gates_passed=4,
        gates_total=4,
        fused_confidence_pct=70.0,
        price_age_hours=48.0,
        stale_threshold_hours=36.0,
    )
    assert out["stale"] is True
    assert out["suppressed"] is True
    assert out["actionable"] is None


def test_attach_uses_primary_gates_only():
    inv = {
        "pattern_score": 91.0,
        "model_confidence_pct": 26,
        "retail_action": {
            "gates": [
                {"id": "valuation", "pass": True},
                {"id": "regime", "pass": False},
                {"id": "momentum", "pass": True},
                {"id": "ml", "pass": False},
                {"id": "confidence", "pass": False},
            ],
        },
    }
    attach_actionable_score(inv, ml_calibration_factor=1.0)
    block = inv["actionable_score"]
    assert block["factors"]["gates_total"] == 4
    assert block["factors"]["gates_passed"] == 2
    assert 18.0 <= block["actionable"] <= 25.0


def test_ml_calibration_factor_discounts_actionable():
    raw = compute_actionable_score(
        80.0,
        gates_passed=4,
        gates_total=4,
        fused_confidence_pct=70.0,
        ml_calibration_factor=1.0,
    )
    discounted = compute_actionable_score(
        80.0,
        gates_passed=4,
        gates_total=4,
        fused_confidence_pct=70.0,
        ml_calibration_factor=0.75,
    )
    assert raw["actionable"] == 80.0
    assert discounted["actionable"] == 60.0
    assert discounted["factors"]["ml_calibration_factor"] == 0.75
