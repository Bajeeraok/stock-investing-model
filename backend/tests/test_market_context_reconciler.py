"""Tests for temperature + regime reconciliation."""
from __future__ import annotations

from signals.market_context_reconciler import reconcile_market_context


def test_risk_off_bull_is_best_buy_not_reduce():
    ctx = reconcile_market_context(
        temperature={"level": "warm", "label": "WARM", "vix": 16.7},
        macro_regime="Risk-Off",
        global_market_regime="STRONG_BULL",
        macro_regime_bundle={"hmm_bear_pct_used": 13.0, "factors": {"vix": 16.7, "hy_oas_bp": 280}},
        credit={"signal": "HEALTHY", "hy_spread_pct": 2.8},
        breadth={"signal": "MIXED", "plain_english": "Mixed participation"},
    )
    assert ctx["quadrant"] == "best_buy_zone"
    assert ctx["grid"]["short"] == "BUY"
    assert ctx["grid"]["medium"] == "BUY"
    assert ctx["is_contradictory"] is False
    assert "not a contradiction" in (ctx.get("coexistence_note") or "").lower() or "fear" in (ctx.get("coexistence_note") or "").lower()


def test_retail_risk_off_warm_uses_cool_overlay():
    from signals.retail_market_decisions import build_retail_market_decisions

    out = build_retail_market_decisions(
        macro_regime="Risk-Off",
        global_market_regime="STRONG_BULL",
        macro_regime_bundle={"factors": {"vix": 16.7}, "hmm_bear_pct_used": 13},
        include_p1=False,
    )
    assert out["market_temperature"]["level"] == "cool"
    assert out["strategy_matrix"]["grid"]["short"] == "BUY"


def test_hot_bull_is_trim_not_buy():
    ctx = reconcile_market_context(
        temperature={"level": "hot", "label": "HOT", "vix": 12.0},
        macro_regime="Risk-On",
        global_market_regime="STRONG_BULL",
        credit={"signal": "HEALTHY"},
    )
    assert ctx["quadrant"] == "hold_and_trim"
    assert ctx["grid"]["short"] == "REDUCE"


def test_cold_bear_is_wait():
    ctx = reconcile_market_context(
        temperature={"level": "cold", "label": "COLD", "vix": 28.0},
        macro_regime="Risk-Off",
        global_market_regime="BEAR",
        credit={"signal": "CAUTION"},
    )
    assert ctx["quadrant"] == "falling_knife"
    assert ctx["grid"]["short"] == "WAIT"
