"""GLD-like long accumulate: tactical stop, tier ladder, valuation gate alignment."""

from __future__ import annotations

import pytest

from signals.horizon_entry_calculator import LongTermInputs, compute_long_term_entry
from signals.retail_action_payload import build_trading_gates


def _gld_like_inputs() -> LongTermInputs:
    """Spot below MA200 but inside harmonized T1; structural floor can sit above spot."""
    return LongTermInputs(
        current_price=390.78,
        fair_value=425.0,
        ma200=405.0,
        week52_low=320.0,
        ml_prob=40.0,
        regime_bull_pct=55.0,
        fundamentals_score=50.0,
        ticker="GLD",
        short_entry_low=385.0,
        short_entry_high=393.0,
        medium_entry_high=395.0,
        atr=6.0,
    )


def test_gld_tactical_stop_below_spot_when_structural_above():
    inp = _gld_like_inputs()
    sig = compute_long_term_entry(inp)
    structural = sig.entry_tiers["structural_invalidation"]["price"]
    assert structural == pytest.approx(round(405.0 * 0.97, 2), abs=0.05)
    assert structural > inp.current_price
    assert sig.stop_loss < inp.current_price
    assert sig.stop_loss_kind == "tactical_tier"
    risk = inp.current_price - sig.stop_loss
    assert risk > 0
    assert sig.risk_reward == pytest.approx((425.0 - inp.current_price) / risk, rel=0.05)


def test_gld_tier_ladder_strict_order():
    inp = _gld_like_inputs()
    sig = compute_long_term_entry(inp)
    tiers = {t["id"]: t for t in sig.entry_tiers["tiers"]}
    assert tiers["T3"]["high"] < tiers["T2"]["low"]


def test_gld_catch_levels_capped_below_fv_without_mos():
    inp = _gld_like_inputs()
    sig = compute_long_term_entry(inp)
    t1_levels = next(t for t in sig.entry_tiers["tiers"] if t["id"] == "T1")["levels"]
    assert t1_levels
    max_catch = max(float(l["price"]) for l in t1_levels)
    assert max_catch <= inp.fair_value * (1 - 0.15) + 0.03
    assert max_catch < inp.fair_value - 1.0


def test_valuation_gate_blocks_at_8pct_mos():
    mos_pct = 100.0 * (425.0 - 390.78) / 390.78
    assert mos_pct == pytest.approx(8.8, abs=0.2)
    gates = build_trading_gates(
        assessment_pct=mos_pct,
        regime_bull_pct=65.0,
        pattern_score=50.0,
        short_ml_prob=40.0,
        rsi=45.0,
        confidence_mid=60.0,
        ticker="GLD",
    )
    val = next(g for g in gates if g["id"] == "valuation")
    assert val["pass"] is False
    # T1 (first-tranche) rung in a bull regime is 10% MOS — still blocks at 8.8%
    assert "10" in val["detail"]
    assert "Deeply" not in val["detail"]
