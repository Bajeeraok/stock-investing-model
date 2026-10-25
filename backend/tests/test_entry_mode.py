"""Conditional entry_mode: hard_lock / starter_only / full_go."""

from __future__ import annotations

import pytest

import signals.retail_action_payload as rap
from signals.retail_action_payload import (
    REGIME_GATE,
    VALUATION_GATE_PASS_PCT,
    build_trading_gates,
    build_unlock_sequence,
    derive_entry_mode,
    enrich_investor_summary_retail_action,
)


def _gates(**kwargs):
    defaults = dict(
        assessment_pct=27.0,
        regime_bull_pct=65.0,
        pattern_score=52.0,
        short_ml_prob=46.0,
        rsi=45.0,
        confidence_mid=60.0,
        include_confidence=False,
    )
    defaults.update(kwargs)
    return build_trading_gates(**defaults)


def test_full_go_when_all_gates_pass():
    gates = _gates(assessment_pct=30.0, regime_bull_pct=70.0, rsi=42.0)
    entry = derive_entry_mode(
        gates=gates,
        assessment_pct=30.0,
        gate_cleared=True,
    )
    assert entry["entry_mode"] == "full_go"
    assert entry["max_sizing_pct"] == 100


@pytest.fixture
def starter_on(monkeypatch):
    monkeypatch.setattr(rap, "STARTER_ONLY_ENABLED", True)


def test_starter_only_disabled_by_default_demotes_to_hard_lock():
    """starter_only measured below SPY in prod snapshots — default is WAIT, not a starter."""
    assert rap.STARTER_ONLY_ENABLED is False
    gates = _gates(assessment_pct=27.0, regime_bull_pct=5.0, rsi=58.0)
    entry = derive_entry_mode(
        gates=gates,
        assessment_pct=27.0,
        gate_cleared=False,
        long_spot={"state": "in_tier", "active_tier_id": "T1"},
    )
    assert entry["entry_mode"] == "hard_lock"
    assert entry["max_sizing_pct"] == 0
    assert "SPY" in entry["entry_mode_detail"]


def test_starter_only_undervalued_stormy_tape(starter_on):
    """Cheap vs FV but HMM 5% — patience phase, starter only."""
    gates = _gates(assessment_pct=27.0, regime_bull_pct=5.0, rsi=58.0)
    entry = derive_entry_mode(
        gates=gates,
        assessment_pct=27.0,
        gate_cleared=False,
        long_spot={"state": "in_tier", "active_tier_id": "T1"},
    )
    assert entry["entry_mode"] == "starter_only"
    assert entry["max_sizing_pct"] == 25
    assert entry["tech_gates_pass"] is False


def test_hard_lock_overvalued():
    gates = _gates(assessment_pct=-8.0, regime_bull_pct=5.0, rsi=58.0)
    entry = derive_entry_mode(
        gates=gates,
        assessment_pct=-8.0,
        gate_cleared=False,
        overall_verdict="WAIT",
    )
    assert entry["entry_mode"] == "hard_lock"
    assert entry["max_sizing_pct"] == 0


def test_hard_lock_no_mos_no_zone():
    gates = _gates(assessment_pct=8.0, regime_bull_pct=5.0)
    entry = derive_entry_mode(
        gates=gates,
        assessment_pct=8.0,
        gate_cleared=False,
    )
    assert entry["entry_mode"] == "hard_lock"


def test_bridge_starter_cap_10_pct(starter_on):
    gates = _gates(assessment_pct=20.0, regime_bull_pct=10.0)
    entry = derive_entry_mode(
        gates=gates,
        assessment_pct=20.0,
        gate_cleared=False,
        zone_context={"in_bridge_band": True, "state": "between_tiers"},
    )
    assert entry["entry_mode"] == "starter_only"
    assert entry["max_sizing_pct"] == 10


def test_unlock_sequence_orders_blockers():
    # rsi=72 is genuinely overbought under the 2026.09.3 momentum_rsi_max=70 ceiling
    # (58 no longer blocks — see test_momentum_rsi_58_passes_in_strong_trend_zone in
    # test_retail_action_payload.py) — keep two real blockers so ordering is exercised.
    gates = _gates(assessment_pct=27.0, regime_bull_pct=5.0, rsi=72.0)
    seq = build_unlock_sequence(gates, stock_bull_pct=5.0)
    assert f"Market Weather ≥{REGIME_GATE}%" in seq
    assert "Momentum Chop" in seq
    assert f"≥{VALUATION_GATE_PASS_PCT:.0f}%" not in seq or "Valuation" in seq


def test_enrich_attaches_entry_mode_and_institutional_conviction(starter_on):
    inv = {
        "fair_value": 461.0,
        "regime_bull_pct": 5.0,
        "pattern_score": 55.0,
        "rsi": 58.0,
        "overall_verdict": "WATCH",
        "horizons": {
            "short": {"ml_prob": 46.0, "entry_zone": {"low": 350, "high": 365}},
            "long": {
                "entry_tiers": {
                    "spot_position": {"state": "in_tier", "active_tier_id": "T1"},
                }
            },
        },
    }
    inst = {
        "role": "conviction_filter",
        "verdict": "supports",
        "conviction_score": 72,
        "buy_the_dip": True,
        "detail": "test",
    }
    out = enrich_investor_summary_retail_action(
        inv, 362.0, ticker="GOOGL", institutional_conviction=inst,
    )
    ra = out["retail_action"]
    assert ra["entry_mode"] in ("starter_only", "hard_lock")
    assert ra.get("institutional_conviction") == inst
    assert "13F" in (ra.get("entry_mode_detail") or "")
