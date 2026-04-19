"""Sell roadmap: larger trim % pairs with higher price zone when bands invert."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.ticker_detail import _reconcile_partial_vs_major_sell_trim_order


def test_swaps_when_upper_band_has_smaller_trim():
    sell_stages = [
        {},
        {},
        {
            "timeline_key": "1_3_months",
            "price_zone_low": 850.0,
            "price_zone_high": 920.0,
            "when_to_sell": "Partial exit",
            "action": "Trim 35%",
            "reason": "Scenario target reached",
            "condition": "Macro scenario …",
            "exit_category": "macro_scenario",
        },
        {
            "timeline_key": "3_6_months",
            "price_zone_low": 835.0,
            "price_zone_high": 842.0,
            "when_to_sell": "Major trim",
            "action": "Sell 50%",
            "reason": "Near fair value",
            "condition": "Valuation …",
            "exit_category": "valuation_fair_value",
        },
    ]
    _reconcile_partial_vs_major_sell_trim_order(sell_stages)
    assert sell_stages[2]["action"] == "Sell 50%"
    assert sell_stages[3]["action"] == "Trim 35%"
    assert sell_stages[2]["when_to_sell"] == "Major trim"
    assert sell_stages[3]["when_to_sell"] == "Partial exit"


def test_no_swap_when_lower_band_is_already_higher_trim():
    sell_stages = [
        {},
        {},
        {
            "price_zone_low": 800.0,
            "price_zone_high": 810.0,
            "action": "Trim 35%",
            "when_to_sell": "Partial exit",
            "reason": "r2",
            "condition": "c2",
            "exit_category": "macro_scenario",
        },
        {
            "price_zone_low": 880.0,
            "price_zone_high": 900.0,
            "action": "Sell 50%",
            "when_to_sell": "Major trim",
            "reason": "r3",
            "condition": "c3",
            "exit_category": "valuation_fair_value",
        },
    ]
    _reconcile_partial_vs_major_sell_trim_order(sell_stages)
    assert sell_stages[2]["action"] == "Trim 35%"
    assert sell_stages[3]["action"] == "Sell 50%"
