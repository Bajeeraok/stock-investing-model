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
