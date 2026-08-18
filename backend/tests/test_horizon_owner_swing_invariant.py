"""Owner vs swing band invariants + packet validation (GLD-style inversion)."""

from __future__ import annotations

from signals.horizon_entry_calculator import (
    LongTermInputs,
    build_all_horizons_payload,
    compute_long_term_entry,
)
from signals.narrative_waterfall import Band, Gate, SignalPacket, build_summary, example_packet_amzn


def _gld_stretched_owner() -> LongTermInputs:
    """Spot above MA50/T1; swing zone is deeper than a squeezed T1 window."""
    return LongTermInputs(
        current_price=404.92,
        fair_value=480.0,
        ma200=411.04,
        week52_low=320.0,
        ml_prob=35.0,
        regime_bull_pct=4.0,
        fundamentals_score=50.0,
        ticker="GLD",
        short_entry_low=387.41,
        short_entry_high=396.96,
        medium_entry_low=377.87,
        medium_entry_high=396.96,
        atr=6.0,
    )


def test_owner_floor_not_above_swing_floor():
    sig = compute_long_term_entry(_gld_stretched_owner())
    assert sig.entry_zone.low <= 377.87 + 0.02
    assert sig.entry_zone.high <= 396.96 + 0.05
    assert "Price ≤" in sig.trigger_buy or "T1 ceiling" in sig.trigger_buy


def test_owner_rr_matches_displayed_stop_and_target():
    sig = compute_long_term_entry(_gld_stretched_owner())
    spot = 404.92
    risk = spot - sig.stop_loss
    reward = sig.target - spot
    assert risk > 0 and reward > 0
    assert sig.risk_reward == round(reward / risk, 2)


def test_payload_cross_horizon_invariant_ok():
    out = build_all_horizons_payload(
        current_price=404.92,
        rsi=62.0,
        atr=6.0,
        vwap=402.0,
        support_level=380.0,
        resistance_level=420.0,
        ma50=387.4,
        ma200=411.04,
        week52_low=320.0,
        volume_ratio=1.0,
        st_ml_prob=30.0,
        mt_ml_prob=32.0,
        lt_ml_prob=35.0,
        regime_bull_pct=4.0,
        pattern_score=50.0,
        fair_value=480.0,
        ticker="GLD",
        fundamentals_score=50.0,
        options_sentiment_score=50.0,
        insider_activity_score=50.0,
    )
    long_ez = out["long"]["entry_zone"]
    mt_ez = out["medium"]["entry_zone"]
    assert long_ez["low"] <= mt_ez["low"] + 0.05
    assert out["long"].get("cross_horizon_invariant_ok") is True
    assert long_ez.get("trigger_kind") == "at_or_below"


def test_pullback_band_ceiling_not_above_spot():
    out = build_all_horizons_payload(
        current_price=45.00,
        rsi=62.0,
        atr=1.2,
        vwap=44.5,
        support_level=42.6,
        resistance_level=48.0,
        ma50=44.8,
        ma200=40.0,
        week52_low=32.0,
        volume_ratio=1.0,
        st_ml_prob=28.0,
        mt_ml_prob=30.0,
        lt_ml_prob=25.0,
        regime_bull_pct=4.0,
        pattern_score=48.0,
        fair_value=78.0,
        ticker="TEST",
        fundamentals_score=50.0,
        options_sentiment_score=50.0,
        insider_activity_score=50.0,
    )
    st = out["short"]["entry_zone"]
    assert st["high"] <= 45.00 + 0.02
    assert "already in" in (out["short"].get("trigger_buy") or "").lower() or st["high"] <= 45.00


def test_owner_stop_sits_below_harmonized_floor():
    sig = compute_long_term_entry(_gld_stretched_owner())
    assert sig.stop_loss < sig.entry_zone.low
    assert sig.stop_loss < 404.92


def test_packet_rejects_invalidation_above_spot():
    pkt = SignalPacket(
        ticker="GLD",
        mode="owner",
        asof="2026-08-17",
        spot=404.92,
        trend="DOWN",
        verdict="WATCH_ZONE",
        score=50,
        gates=[Gate("valuation", False, {"text": "mos", "mos_pct": 8.0, "required_pct": 25.0})],
        entry_band=Band(377.87, 396.96),
        stop=383.0,
        invalidation=399.71,
        target=480.0,
        rr=13.0,
        unlock_conditions=["Valuation clears"],
        hmm_bull_pct=4.0,
    )
    errs = pkt.validate()
    assert any("invalidation" in e for e in errs)


def test_packet_rejects_rr_mismatch():
    pkt = SignalPacket(
        ticker="X",
        mode="scout",
        asof="2026-08-17",
        spot=45.0,
        trend="DOWN",
        verdict="WATCH_ZONE",
        score=40,
        gates=[],
        entry_band=Band(42.0, 44.5),
        stop=41.50,
        invalidation=41.40,
        target=77.7,
        rr=2.0,
        hmm_bull_pct=4.0,
    )
    errs = pkt.validate()
    assert any("R:R" in e for e in errs)


def test_example_packet_still_publishes():
    out = build_summary(example_packet_amzn(), llm=None)
    assert out["status"] == "ok"
    assert out.get("layer2_guard_violations") in (None, [])
