"""Long-term tier ladder must sync with horizon entry_zone and roadmap core zone."""
from __future__ import annotations

from api.ticker_detail import _roadmap_core_zone_3_to_6
from signals.horizon_entry_calculator import LongTermInputs, compute_long_term_entry, resolve_active_tier


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
    from signals.horizon_entry_calculator import EntryTier

    t1 = EntryTier("T1", "T1", "", 280.0, 310.0, 0, 0, "", "M", "#fff", True, 20.0)
    t2 = EntryTier("T2", "T2", "", 380.0, 404.0, 0, 0, "", "H", "#fff", False, None)
    t3 = EntryTier("T3", "T3", "", 170.0, 186.0, 0, 0, "", "S", "#fff", True, 50.0)
    active = resolve_active_tier([t1, t2, t3], 387.66)
    assert active is not None
    assert active.id == "T2"
