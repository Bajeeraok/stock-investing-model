"""BLK-class asset managers, ticker normalization, CRSP pre-biotech, suppressed tier anchors."""
from __future__ import annotations

from signals.fair_value_estimator import StockType, _reconcile_model_vs_street, estimate_fair_value
from signals.fv_router import normalize_ticker_key, route_fair_value
from signals.horizon_entry_calculator import LongTermInputs, compute_long_term_entry


def test_blk_routed_to_asset_manager_suppression():
    r = route_fair_value("BLK", ttm_eps=40.0, ntm_eps=42.0, ttm_pe=26.0, sector="Asset Management")
    assert r.fv_suppressed is True
    assert "ASSET MANAGER" in r.fv_suppressed_reason


def test_brk_dot_normalized_to_insurer_suppression():
    r = route_fair_value("BRK.B", ttm_eps=20.0, ntm_eps=22.0, ttm_pe=18.0)
    assert r.fv_suppressed is True
    assert "INSURER" in r.fv_suppressed_reason


def test_crsp_prebiotech_suppressed():
    r = route_fair_value("CRSP", ttm_eps=-2.0, ntm_eps=-1.5, ttm_pe=None)
    assert r.fv_suppressed is True
    assert "BIOTECH" in r.fv_suppressed_reason.upper()


def test_normalize_ticker_key():
    assert normalize_ticker_key("brk.b") == "BRK-B"
    assert normalize_ticker_key(" BRK-B ") == "BRK-B"


def test_model_above_street_blend_pulls_down():
    fv, notes = _reconcile_model_vs_street(
        1432.0,
        1251.0,
        StockType.GROWTH,
        {"street_blend_trigger_above_pct": 0.12, "street_blend_above_weight": 0.45},
    )
    assert fv < 1432.0
    assert fv > 1251.0
    assert any("above street" in n.lower() for n in notes)


def test_growth_name_above_street_end_to_end_capped():
    """GROWTH peg_blend with optimistic inputs — blend + analyst cap keep FV near street."""
    street = 1251.0
    r = estimate_fair_value(
        current_price=1200.0,
        ttm_pe=32.0,
        sector_pe=20.0,
        revenue_growth_pct=28.0,
        earnings_growth_pct=32.0,
        net_margin_pct=35.0,
        de_ratio=0.3,
        forward_pe=19.0,
        sector_forward_pe=30.0,
        analyst_target=street,
        guardrails={
            "street_blend_trigger_above_pct": 0.12,
            "street_blend_above_weight": 0.45,
            "analyst_mean_cap_mult": 1.10,
        },
    )
    assert r.fair_value <= street * 1.11
    assert any("above street" in n.lower() or "capped" in n.lower() for n in r.notes)


def test_suppressed_long_term_tier2_street_anchored_labels():
    sig = compute_long_term_entry(
        LongTermInputs(
            current_price=1100.0,
            fair_value=1432.0,  # stale model FV — should be overridden by street anchor
            ma200=1059.0,
            week52_low=900.0,
            ml_prob=40.0,
            regime_bull_pct=55.0,
            fundamentals_score=70.0,
            ticker="BLK",
            fv_model_suppressed=True,
            fv_street_anchor_usd=1251.0,
            fv_suppressed_reason="ASSET MANAGER — P/E vs sector misstates fee-based earnings",
        )
    )
    t2 = next(t for t in sig.entry_tiers["tiers"] if t["id"] == "T2")
    assert "street" in t2["label"].lower()
    assert "street" in t2["description"].lower()
    assert any("Model FV unavailable" in w for w in sig.warnings)
    # T2 center should be below street MOS, not inflated model 1432 MOS (~1006)
    assert t2["high"] < 1200.0
