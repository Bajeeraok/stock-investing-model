"""Stop/tier copy must not conflate MA50 swing stops with MA200 Tier 1 bands."""

from __future__ import annotations

from signals.horizon_entry_calculator import build_all_horizons_payload


def _goog_like_payload():
    """Shape similar to extended GOOGL: spot above MA50, MA200 far below."""
    return build_all_horizons_payload(
        current_price=382.97,
        rsi=58.0,
        atr=8.5,
        vwap=380.0,
        support_level=370.0,
        resistance_level=395.0,
        ma50=387.04,
        ma200=295.50,
        week52_low=140.0,
        volume_ratio=1.0,
        st_ml_prob=46.0,
        mt_ml_prob=42.0,
        lt_ml_prob=55.0,
        regime_bull_pct=1.0,
        pattern_score=52.0,
        fair_value=461.0,
        options_sentiment_score=50.0,
        insider_activity_score=50.0,
        fundamentals_score=72.0,
        ticker="GOOGL",
        tier2_mos_pct=15.0,
    )


def test_swing_stop_framing_not_ma200_tier():
    out = _goog_like_payload()
    short = out["short"]
    framing = (short.get("stop_loss_framing") or "").lower()
    assert "not ma200" in framing
    assert "tier 1 ma200 zone" in framing
    t1_lo = round(295.50 * 0.95, 2)
    t1_hi = round(295.50 * 1.05, 2)
    assert f"{t1_lo:.2f}" in short["stop_loss_framing"] or f"{t1_lo}" in short["stop_loss_framing"]
    assert f"{t1_hi:.2f}" in short["stop_loss_framing"] or f"{t1_hi}" in short["stop_loss_framing"]
    # Stop should sit near MA50 band, not MA200 tier
    assert short["stop_loss"] > t1_hi + 10


def test_build_stop_framing_is_ma50_not_ma200():
    out = _goog_like_payload()
    medium = out["medium"]
    framing = medium.get("stop_loss_framing") or ""
    assert "MA50" in framing
    assert "Not Tier 1 MA200" in framing
    assert medium["stop_loss_kind"] == "build_ma50"


def test_tier2_above_full_mos_ceiling_flagged():
    out = _goog_like_payload()
    long_h = out["long"]
    ca = long_h["entry_tiers"]["current_assessment"]
    min_buy = ca["min_price_to_buy"]
    assert min_buy is not None
    assert 382.97 > float(min_buy)
    if long_h["entry_tiers"].get("active_tier_id") == "T2":
        assert ca.get("above_full_mos_ceiling") is True
        assert ca.get("position_mode") == "partial_only"
        joined = " ".join(long_h.get("warnings") or [])
        assert "partial position only" in joined.lower()


def test_googl_between_tiers_gap_at_358():
    """Extended GOOGL: spot between MA200 T1 and FV-based T2 — not 'below T2 low' chase."""
    out = build_all_horizons_payload(
        current_price=358.99,
        rsi=58.0,
        atr=8.5,
        vwap=358.0,
        support_level=350.0,
        resistance_level=395.0,
        ma50=387.04,
        ma200=295.50,
        week52_low=140.0,
        volume_ratio=1.0,
        st_ml_prob=46.0,
        mt_ml_prob=42.0,
        lt_ml_prob=55.0,
        regime_bull_pct=45.0,
        pattern_score=52.0,
        fair_value=461.0,
        options_sentiment_score=50.0,
        insider_activity_score=50.0,
        fundamentals_score=72.0,
        ticker="GOOGL",
        tier2_mos_pct=15.0,
    )
    et = out["long"]["entry_tiers"]
    spot = et.get("spot_position") or {}
    assert spot.get("state") == "between_tiers"
    assert spot.get("floor_tier_id") == "T1"
    assert spot.get("ceiling_tier_id") == "T2"
    assert et.get("target_tier_id") == "T1"
    assert et.get("active_tier_id") is None
    trigger = out["long"].get("trigger_buy") or ""
    assert "pullback to" in trigger.lower() or "hold at spot" in trigger.lower()
    assert "T1" in trigger or "Tier 1" in trigger
    assert 358.99 > et["tiers"][0]["high"]  # above T1
    t2 = next(t for t in et["tiers"] if t["id"] == "T2")
    assert 358.99 < t2["low"]  # below T2


def test_bridge_band_inside_gap():
    from signals.horizon_entry_calculator import build_bridge_band

    bridge = build_bridge_band(310.0, 380.0, 358.0, band_label="T1.5 test")
    assert bridge is not None
    assert bridge["low"] <= 358.0 <= bridge["high"]
    assert len(bridge["levels"]) >= 3
    assert bridge.get("max_allocation_pct") == 10


def test_googl_owner_tiers_capped_to_swing_top_at_358():
    out = build_all_horizons_payload(
        current_price=358.99,
        rsi=58.0,
        atr=8.5,
        vwap=355.0,
        support_level=350.0,
        resistance_level=395.0,
        ma50=340.0,
        ma200=295.50,
        week52_low=140.0,
        volume_ratio=1.0,
        st_ml_prob=46.0,
        mt_ml_prob=42.0,
        lt_ml_prob=55.0,
        regime_bull_pct=45.0,
        pattern_score=52.0,
        fair_value=461.0,
        options_sentiment_score=50.0,
        insider_activity_score=50.0,
        fundamentals_score=72.0,
        ticker="GOOGL",
        tier2_mos_pct=15.0,
    )
    # Owner adds never sit above the swing top: the FV-MOS Tier 2 band (would reach ~$403)
    # is capped to the medium zone high, so spot $358.99 is above every owner tier and the
    # long plan waits for the same pullback the swing plan does (no "buy higher" bridge).
    et = out["long"]["entry_tiers"]
    tiers = {t["id"]: t for t in et["tiers"]}
    med_hi = out["medium"]["entry_zone"]["high"]
    assert tiers["T2"]["high"] <= med_hi + 1e-6
    assert tiers["T1"]["high"] <= med_hi + 1e-6
    assert tiers["T2"]["high"] > tiers["T1"]["high"] > tiers["T3"]["high"]
    assert et["spot_position"].get("state") == "above_all"
    assert out["long"]["entry_zone"]["high"] <= med_hi + 1e-6


def test_short_swing_between_bands_and_catch_levels():
    out = build_all_horizons_payload(
        current_price=358.99,
        rsi=58.0,
        atr=8.5,
        vwap=355.0,
        support_level=350.0,
        resistance_level=395.0,
        ma50=340.0,
        ma200=295.50,
        week52_low=140.0,
        volume_ratio=1.0,
        st_ml_prob=46.0,
        mt_ml_prob=42.0,
        lt_ml_prob=55.0,
        regime_bull_pct=45.0,
        pattern_score=52.0,
        fair_value=461.0,
        options_sentiment_score=50.0,
        insider_activity_score=50.0,
        fundamentals_score=72.0,
        ticker="GOOGL",
        tier2_mos_pct=15.0,
    )
    st_ez = out["short"]["entry_zone"]
    mt_ez = out["medium"]["entry_zone"]
    assert st_ez.get("levels") and len(st_ez["levels"]) >= 3
    assert mt_ez.get("levels") and len(mt_ez["levels"]) >= 3
    st_hi = max(st_ez["low"], st_ez["high"])
    mt_lo = min(mt_ez["low"], mt_ez["high"])
    if 358.99 > st_hi and 358.99 < mt_lo:
        assert st_ez["spot_position"]["state"] == "between_horizon_bands"
        assert st_ez["spot_position"]["cross_gap"]["floor_horizon"] == "short"
        assert st_ez["spot_position"]["cross_gap"]["ceiling_horizon"] == "medium"
