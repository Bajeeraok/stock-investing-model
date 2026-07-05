"""Tests for swing_setup play sheet builder."""

from __future__ import annotations

import pytest

from signals.retail_action_payload import enrich_investor_summary_retail_action
from signals.swing_setup import build_swing_setup


def _base_investor_out(*, regime_bull: float = 65.0, rsi: float = 44.0, ml_prob: float = 30.0) -> dict:
    return {
        "fair_value": 150.0,
        "overall_verdict": "WATCH",
        "regime_bull_pct": regime_bull,
        "pattern_score": 55.0,
        "rsi": rsi,
        "horizons": {
            "short": {
                "ml_prob": ml_prob,
                "entry_zone": {"low": 98.0, "high": 102.0},
                "stop_loss": 94.0,
                "target": 112.0,
                "risk_reward": 1.4,
            },
            "medium": {
                "ml_prob": ml_prob,
                "verdict": "BUY",
                "entry_zone": {"low": 95.0, "high": 100.0},
                "stop_loss": 88.0,
                "target": 118.0,
                "risk_reward": 1.2,
            },
        },
    }


def test_swing_setup_no_go_when_gates_fail():
    inv = _base_investor_out(regime_bull=38.0, rsi=62.0, ml_prob=22.0)
    enrich_investor_summary_retail_action(inv, 100.0)
    out = build_swing_setup(
        ticker="NVDA",
        investor_out=inv,
        current_price=100.0,
        response={
            "high_52w": 110.0,
            "earnings": {"days_until": 8, "date": "2026-05-27"},
            "ma20": 99.0,
            "ma50": 95.0,
            "ma200": 90.0,
            "volume_ratio": 0.7,
            "trend_score": 67.0,
            "atr14": 2.5,
        },
        market_context={"primary_message": "Macro overlay cautious — wait for dip."},
    )
    assert out is not None
    assert out["go_no_go"] == "no_go"
    assert out["setup_quality"]["passed"] < out["setup_quality"]["total"]
    assert out["sizing"] is None
    assert len(out["triggers"]["wait"]) >= 1
    assert out["earnings_caveat"] is not None


def test_swing_setup_go_with_sizing_when_all_gates_pass():
    inv = _base_investor_out(regime_bull=68.0, rsi=42.0, ml_prob=35.0)
    enrich_investor_summary_retail_action(inv, 100.0)
    out = build_swing_setup(
        ticker="AAPL",
        investor_out=inv,
        current_price=100.0,
        response={
            "high_52w": 108.0,
            "ma20": 99.0,
            "ma50": 96.0,
            "ma200": 88.0,
            "volume_ratio": 0.75,
            "trend_score": 72.0,
            "atr14": 2.0,
        },
        config={"risk_sizing": {"risk_pct": 2.0}},
    )
    assert out is not None
    assert out["go_no_go"] == "go"
    assert out["setup_quality"]["label"] == "HIGH"
    assert out["sizing"] is not None
    assert out["sizing"]["shares_example"] > 0
    assert out["trade"]["entry_low"] == 98.0
    assert out.get("swing_classification") is not None
    assert out["trade"]["stop"] == pytest.approx(94.0, abs=0.15)
    assert not out["triggers"]["wait"]


def test_swing_setup_returns_none_without_short_levels():
    inv = {"horizons": {"short": {"entry_zone": {}}}, "retail_action": {"gates": []}}
    assert build_swing_setup(ticker="X", investor_out=inv, current_price=100.0) is None
