"""Tests for swing setup classifier."""
from __future__ import annotations

from signals.swing_classifier import (
    SwingSetupType,
    build_swing_classification_bundle,
    classify_swing_setup,
    compute_swing_score,
    extract_swing_inputs,
)


def test_dip_to_ma_mrvl_like():
    inp = {
        "price": 266.0,
        "rsi": 53.0,
        "vol_ratio": 0.5,
        "golden_cross": True,
        "above_ma50": True,
        "momentum_shift": 45.0,
        "trend_strength": 100.0,
        "pattern_score": 45.0,
        "ma21": 260.0,
        "ma50": 213.0,
        "atr": 8.0,
        "near_resistance": False,
    }
    st, reasons = classify_swing_setup(inp)
    assert st == SwingSetupType.DIP_TO_MA
    assert reasons
    score = compute_swing_score(inp, st)
    assert score["verdict"] in ("SWING_SIGNAL", "WATCH")
    assert score["signal_basis"] == "technical"


def test_oversold_bounce():
    inp = {
        "price": 100.0,
        "rsi": 35.0,
        "vol_ratio": 0.6,
        "golden_cross": True,
        "above_ma50": False,
        "trend_strength": 40.0,
        "pattern_score": 50.0,
        "recent_low": 95.0,
    }
    st, _ = classify_swing_setup(inp)
    assert st == SwingSetupType.OVERSOLD_BOUNCE


def test_breakout():
    inp = {
        "price": 100.0,
        "rsi": 58.0,
        "vol_ratio": 1.8,
        "momentum_shift": 65.0,
        "trend_strength": 75.0,
        "pattern_score": 60.0,
        "near_resistance": True,
        "resistance": 101.0,
        "atr": 2.0,
    }
    st, _ = classify_swing_setup(inp)
    assert st == SwingSetupType.BREAKOUT


def test_divergence_note_when_long_wait():
    bundle = build_swing_classification_bundle(
        investor_out={
            "overall_verdict": "WAIT",
            "rsi": 53.0,
            "pattern_score": 45.0,
            "regime_bull_pct": 68.0,
            "horizons": {"short": {"ml_prob": 30.0}},
        },
        response={
            "close": 266.0,
            "ma20": 260.0,
            "ma50": 213.0,
            "ma200": 200.0,
            "volume_ratio": 0.5,
            "trend_score": 100.0,
            "atr14": 8.0,
        },
        current_price=266.0,
        entry_low=264.0,
        entry_high=268.0,
    )
    assert bundle["setup_type"] == "dip_to_ma"
    if bundle["swing_score"]["verdict"] == "SWING_SIGNAL":
        assert bundle.get("divergence_note")
        assert "tactical swing" in bundle["divergence_note"].lower()
    assert bundle.get("exit_plan")


def test_extract_inputs_from_response():
    inp = extract_swing_inputs(
        investor_out={"rsi": 53.0, "pattern_score": 45.0, "regime_bull_pct": 68.0},
        response={
            "ma20": 260.0,
            "ma50": 213.0,
            "ma200": 200.0,
            "volume_ratio": 0.5,
            "trend_score": 100.0,
            "close": 266.0,
        },
        current_price=266.0,
    )
    assert inp["golden_cross"] is True
    assert inp["above_ma50"] is True
    assert inp["vol_ratio"] == 0.5
