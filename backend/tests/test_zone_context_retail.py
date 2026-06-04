"""Zone-aware retail action titles and unlock copy."""
from __future__ import annotations

from signals.retail_action_payload import (
    build_unlock_summary,
    build_zone_context,
    derive_zone_aware_action_title,
)


def test_watch_zone_action_title():
    title, light = derive_zone_aware_action_title(
        "WAIT",
        False,
        long_spot={"state": "between_tiers", "in_bridge_band": False},
    )
    assert title == "WATCH ZONE"
    assert light == "yellow"


def test_in_tier_accumulate():
    title, light = derive_zone_aware_action_title(
        "WAIT",
        False,
        long_spot={"state": "in_tier", "active_tier_id": "T2"},
    )
    assert "ACCUMULATE" in title
    assert "T2" in title


def test_unlock_summary_regime():
    gates = [
        {"id": "regime", "label": "MARKET WEATHER", "pass": False, "blocker_weight": 40},
    ]
    zc = {"gap_low": 317.0, "gap_high": 373.0, "in_bridge_band": False}
    line = build_unlock_summary(gates, stock_bull_pct=1.0, zone_context=zc)
    assert line is not None
    assert "HMM bull" in line
    assert "317" in line


def test_build_zone_context_between_tiers():
    inv = {
        "horizons": {
            "long": {
                "entry_tiers": {
                    "spot_position": {
                        "state": "between_tiers",
                        "floor_band_high": 340.0,
                        "ceiling_band_low": 380.0,
                        "bridge_band": {
                            "low": 346.0,
                            "high": 356.0,
                            "levels": [{"id": "l1", "label": "a", "price": 350.0}],
                        },
                    }
                }
            }
        }
    }
    zc = build_zone_context(inv, 358.0)
    assert zc is not None
    assert zc["zone_name"] == "Watch Zone"
    assert zc["bridge_low"] == 346.0
