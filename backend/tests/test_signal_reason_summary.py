"""Tests for signal_reason_summary."""
from __future__ import annotations

from signals.retail_action_payload import build_trading_gates
from signals.signal_reason_summary import build_signal_reason_summary, _days_to_plain


def test_days_to_plain_buckets():
    assert "week" in _days_to_plain(4)
    assert "2–4 weeks" in _days_to_plain(21)
    assert "month" in _days_to_plain(45)


def test_wait_plain_when_gates_blocked():
    gates = build_trading_gates(
        assessment_pct=8.0,
        regime_bull_pct=55.0,
        pattern_score=50.0,
        short_ml_prob=30.0,
        rsi=58.0,
        confidence_mid=60.0,
        include_confidence=False,
        ticker="AAPL",
    )
    out = build_signal_reason_summary(
        ticker="AAPL",
        gates=gates,
        assessment_pct=8.0,
        current_price=180.0,
        fair_value=195.0,
        regime_bull_pct=55.0,
        rsi=58.0,
        short_ml_prob=30.0,
        entry_mode="starter_only",
        gate_cleared=False,
        regime_transition_days=12,
    )
    assert out["headline"]
    assert out["wait_plain"]
    assert len(out["factors"]) >= 3
    assert out["top_blocker"] in ("regime", "momentum", "valuation", "ml", "rsi_heat")


def test_no_wait_when_full_go():
    gates = build_trading_gates(
        assessment_pct=30.0,
        regime_bull_pct=72.0,
        pattern_score=55.0,
        short_ml_prob=45.0,
        rsi=42.0,
        confidence_mid=70.0,
        include_confidence=False,
    )
    out = build_signal_reason_summary(
        gates=gates,
        assessment_pct=30.0,
        gate_cleared=True,
        entry_mode="full_go",
    )
    assert out["wait_plain"] is None
    assert "align" in out["headline"].lower()


def test_confidence_layers_merge():
    gates = build_trading_gates(
        assessment_pct=5.0,
        regime_bull_pct=50.0,
        pattern_score=40.0,
        short_ml_prob=20.0,
        rsi=55.0,
        confidence_mid=50.0,
        include_confidence=False,
    )
    confidence = {
        "breakdown": {
            "regime_hmm": {"score": 0.35, "weight": 0.15, "available": True, "label": "Bearish HMM"},
            "fundamental_score": {"score": 0.72, "weight": 0.20, "available": True, "label": "Solid FV gap"},
            "nlp_sentiment": {"score": 0.55, "weight": 0.10, "available": True, "label": "Mixed headlines"},
        },
        "labels": {},
    }
    out = build_signal_reason_summary(
        gates=gates,
        assessment_pct=5.0,
        gate_cleared=False,
        confidence=confidence,
    )
    ids = {f["id"] for f in out["factors"]}
    assert "fundamental_score" in ids or "valuation" in ids
