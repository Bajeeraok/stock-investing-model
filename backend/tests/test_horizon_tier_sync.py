"""Long-term tier ladder must sync with horizon entry_zone and roadmap core zone."""
from __future__ import annotations

from api.ticker_detail import _roadmap_core_zone_3_to_6
from signals.horizon_entry_calculator import (
    EntryTier,
    LongTermInputs,
    compute_long_term_entry,
    resolve_active_tier,
    resolve_target_tier_id,
)


def _sample_long_inputs(**overrides) -> LongTermInputs:
    base = dict(
        current_price=387.66,
        fair_value=480.0,
        ma200=295.02,
        week52_low=178.0,
        ml_prob=30.0,
        regime_bull_pct=0.0,
        fundamentals_score=72.0,
        ticker="TEST",
        tier2_mos_pct=15.0,
    )
    base.update(overrides)
    return LongTermInputs(**base)


def test_entry_zone_matches_active_tier2():
    # FV ~461 → 15% MOS Tier 2 center ~392 → band ~380–404 (matches retail screenshot shape)
    inp = _sample_long_inputs(fair_value=461.0)
    sig = compute_long_term_entry(inp)
    tiers = sig.entry_tiers["tiers"]
    t2 = next(t for t in tiers if t["id"] == "T2")
    assert inp.current_price >= t2["low"] and inp.current_price <= t2["high"]
    assert sig.entry_tiers["active_tier_id"] == "T2"
    assert sig.entry_zone.low == t2["low"]
    assert sig.entry_zone.high == t2["high"]
    assert "Tier 2" in sig.trigger_buy or "T2" in sig.trigger_buy
    assert sig.verdict in ("WATCH", "BUY")


def test_roadmap_core_zone_uses_tier2_when_inside():
    lo, hi, when, cond = _roadmap_core_zone_3_to_6(
        current_price=387.66,
        ma200=295.02,
        t1_lo=280.27,
        t1_hi=309.77,
        t2_lo=380.67,
        t2_hi=404.22,
        low_52w=178.0,
    )
    assert lo == 380.67
    assert hi == 404.22
    assert "Tier 2" in when
    assert "Tier 2" in cond


def test_resolve_active_tier_prefers_t2():
    t1 = EntryTier("T1", "T1", "", 280.0, 310.0, 0, 0, "", "M", "#fff", True, 20.0)
    t2 = EntryTier("T2", "T2", "", 380.0, 404.0, 0, 0, "", "H", "#fff", False, None)
    t3 = EntryTier("T3", "T3", "", 170.0, 186.0, 0, 0, "", "S", "#fff", True, 50.0)
    active = resolve_active_tier([t1, t2, t3], 387.66)
    assert active is not None
    assert active.id == "T2"


def test_roadmap_core_zone_prefers_medium_entry_zone_over_tier_blend():
    """The actual bug fix: when horizons.medium.entry_zone is available, the roadmap's core
    zone must use it directly — not the long-tier/MA200 blend — even when spot sits inside a
    long-term tier that would otherwise win. Regression for the confirmed-live SNDK case where
    Position Build showed $1,501.59-$1,577.43 and the Buy Roadmap showed $1,435.47-$1,577.43
    for what both UI tabs presented as the same ~1-3 month window."""
    lo, hi, when, cond = _roadmap_core_zone_3_to_6(
        current_price=387.66,
        ma200=295.02,
        t1_lo=280.27,
        t1_hi=309.77,
        t2_lo=380.67,
        t2_hi=404.22,
        low_52w=178.0,
        medium_lo=350.00,
        medium_hi=375.00,
    )
    assert lo == 350.00
    assert hi == 375.00
    assert "medium-term" in when.lower()
    assert "same medium-term entry band" in cond.lower()


def test_roadmap_core_zone_falls_back_to_tier_blend_when_medium_zone_missing():
    """medium_lo/medium_hi default to None — existing callers / the pre-fix behavior for
    degraded data (no medium.entry_zone available) must be unaffected."""
    lo, hi, when, cond = _roadmap_core_zone_3_to_6(
        current_price=387.66,
        ma200=295.02,
        t1_lo=280.27,
        t1_hi=309.77,
        t2_lo=380.67,
        t2_hi=404.22,
        low_52w=178.0,
    )
    assert lo == 380.67
    assert hi == 404.22
    assert "Tier 2" in when


def test_roadmap_core_zone_ignores_non_positive_medium_zone():
    """A zero/negative medium_lo or medium_hi must not be trusted as real data — falls
    through to the tier blend rather than returning a nonsensical zero-width or negative band."""
    lo, hi, when, cond = _roadmap_core_zone_3_to_6(
        current_price=387.66,
        ma200=295.02,
        t1_lo=280.27,
        t1_hi=309.77,
        t2_lo=380.67,
        t2_hi=404.22,
        low_52w=178.0,
        medium_lo=0.0,
        medium_hi=0.0,
    )
    assert lo == 380.67
    assert hi == 404.22


def test_resolve_target_tier_nearest_between_t1_and_t2():
    """Spot just below T2 should target T2, not T3 stress sleeve or T1 below."""
    t1 = EntryTier("T1", "T1", "", 284.71, 314.69, 0, 0, "", "M", "#fff", True, 20.0)
    t2 = EntryTier("T2", "T2", "", 381.92, 405.54, 0, 0, "", "H", "#fff", False, None)
    t3 = EntryTier("T3", "T3", "", 170.10, 186.30, 0, 0, "", "S", "#fff", True, 50.0)
    assert resolve_target_tier_id([t1, t2, t3], 380.34) == "T2"
