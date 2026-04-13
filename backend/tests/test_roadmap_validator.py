"""Critical roadmap validator / fixer behavior."""

from __future__ import annotations

from signals.roadmap_validator import (
    RoadmapFixer,
    RoadmapInput,
    RoadmapValidator,
    apply_roadmap_consistency,
    trade_roadmap_stages_to_input,
    BuyTier,
    PriceZone,
    SellTier,
)


def test_sell_hard_stop_high_only_is_single_level_not_zero_spread():
    """API uses price_zone_high only for hard stop; mapping must not invent low=0."""
    sell = [
        {
            "timeline_key": "immediate",
            "label": "Immediate",
            "when_to_sell": "Hard stop",
            "price_zone_low": None,
            "price_zone_high": 415.27,
            "condition": "Breaks 52w low",
            "action": "Exit 100%",
        }
    ]
    inp = trade_roadmap_stages_to_input(
        "X",
        current_price=440.0,
        fair_value=600.0,
        regime_bull_pct=50.0,
        ma50=430.0,
        ma200=400.0,
        week52_low=380.0,
        week52_high=450.0,
        atr=5.0,
        scenario_target=500.0,
        buy_stages=[],
        sell_stages=sell,
    )
    z = inp.sell_tiers[0].zone
    assert z is not None
    assert z.low == 415.27 and z.high == 415.27


def test_rc1_aligns_scenario_to_full_target_midpoint():
    sell_tiers = [
        SellTier("6–12 months", "Full target", PriceZone(100.0, 110.0), "fv"),
    ]
    r = RoadmapInput(
        ticker="X",
        current_price=50.0,
        fair_value=105.0,
        regime_bull_pct=50.0,
        ma50=55.0,
        ma200=60.0,
        week52_low=40.0,
        week52_high=120.0,
        atr=2.0,
        scenario_target=80.0,
        buy_tiers=[],
        sell_tiers=sell_tiers,
    )
    RoadmapFixer().fix_all(r)
    assert abs(r.scenario_target - 105.0) < 0.01


def test_rc2_preserves_band_width_when_flooring_at_fv():
    r = RoadmapInput(
        ticker="X",
        current_price=50.0,
        fair_value=100.0,
        regime_bull_pct=50.0,
        ma50=55.0,
        ma200=60.0,
        week52_low=40.0,
        week52_high=120.0,
        atr=2.0,
        scenario_target=100.0,
        buy_tiers=[],
        sell_tiers=[
            SellTier("m", "Partial exit", PriceZone(90.0, 110.0), "x"),
        ],
    )
    RoadmapFixer()._fix_fv_sell_zones(r)
    t = r.sell_tiers[0]
    assert t.zone is not None
    assert t.zone.low == 100.0
    assert abs((t.zone.high - t.zone.low) - 20.0) < 0.02


def test_apply_roadmap_consistency_sets_roadmap_auto_adjusted():
    buy = [
        {
            "timeline_key": "today",
            "label": "Today",
            "when_to_act": "Watch only",
            "price_zone_low": 100.0,
            "price_zone_high": 100.0,
            "condition": "",
            "conviction": "None",
            "position_pct": 0,
        }
    ]
    sell = [
        {
            "timeline_key": "6_12",
            "label": "6–12 months",
            "when_to_sell": "Full target",
            "price_zone_low": 200.0,
            "price_zone_high": 220.0,
            "condition": "",
            "action": "Sell",
        }
    ]
    meta = apply_roadmap_consistency(
        "X",
        buy,
        sell,
        current_price=100.0,
        fair_value=210.0,
        regime_bull_pct=50.0,
        ma50=100.0,
        ma200=100.0,
        week52_low=50.0,
        week52_high=250.0,
        atr=2.0,
        scenario_target=50.0,
        apply_fixes=True,
    )
    assert meta.get("roadmap_auto_adjusted") is True
    assert meta["scenario_target"] == 210.0


def test_rc5_skips_continuity_when_prev_high_nonpositive():
    r = RoadmapInput(
        ticker="X",
        current_price=50.0,
        fair_value=60.0,
        regime_bull_pct=50.0,
        ma50=55.0,
        ma200=60.0,
        week52_low=40.0,
        week52_high=80.0,
        atr=1.0,
        scenario_target=60.0,
        buy_tiers=[
            BuyTier("a", "Add", PriceZone(10.0, 0.0), "", "Medium", 25),
            BuyTier("b", "Add", PriceZone(5.0, 50.0), "", "Medium", 25),
        ],
        sell_tiers=[],
    )
    issues = RoadmapValidator().validate(r)
    codes = [x[0] for x in issues]
    assert "RC-5" in codes
