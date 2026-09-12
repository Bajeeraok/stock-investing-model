"""Zone-aware retail action titles and unlock copy."""
from __future__ import annotations

from signals.retail_action_payload import (
    build_unlock_summary,
    build_zone_context,
    derive_zone_aware_action_title,
    enrich_investor_summary_retail_action,
)


def test_watch_zone_action_title():
    title, light = derive_zone_aware_action_title(
        "WAIT",
        False,
        long_spot={"state": "between_tiers", "in_bridge_band": False},
    )
    assert title == "WATCH ZONE"
    assert light == "yellow"


def test_in_tier_wait_for_gates_when_blocked():
    title, light = derive_zone_aware_action_title(
        "WAIT",
        False,
        long_spot={"state": "in_tier", "active_tier_id": "T2"},
    )
    assert "WAIT FOR GATES" in title
    assert "T2" in title
    assert "ACCUMULATE" not in title
    assert light == "yellow"


def test_in_tier_accumulate_when_gates_clear():
    title, light = derive_zone_aware_action_title(
        "BUY",
        True,
        long_spot={"state": "in_tier", "active_tier_id": "T2"},
    )
    assert "ACCUMULATE" in title
    assert "T2" in title
    assert light == "green"


def test_unlock_summary_regime():
    gates = [
        {"id": "regime", "label": "MARKET WEATHER", "pass": False, "blocker_weight": 40},
    ]
    zc = {"gap_low": 317.0, "gap_high": 373.0, "in_bridge_band": False}
    line = build_unlock_summary(gates, stock_bull_pct=1.0, zone_context=zc)
    assert line is not None
    assert "HMM bull" in line
    assert "317" in line


def test_unlock_summary_already_in_st_band():
    gates = [
        {"id": "regime", "label": "MARKET WEATHER", "pass": False, "blocker_weight": 40},
        {"id": "momentum", "label": "Momentum Chop", "pass": False, "blocker_weight": 20},
    ]
    st = {"low": 202.0, "high": 206.0}
    line = build_unlock_summary(
        gates,
        stock_bull_pct=0.0,
        st_band=st,
        current_price=205.1,
    )
    assert line is not None
    assert "Already" in line
    assert "202" in line
    assert "206" in line
    assert "HMM bull" in line
    assert "price enters" not in line.lower()


def test_action_title_by_mode_does_not_leak_owner_tier_to_scout_or_swing():
    """Regression: SPCX showed 'T2 IN RANGE · WAIT FOR GATES' in Scout AND Swing mode —
    an owner-only long-term-tier label. The flat action_title always prefers long_spot
    whenever long-term tiers exist (basically every ticker), regardless of persona.
    action_title_by_mode must give scout/swing only their own horizon's zone."""
    inv = {
        "fair_value": 200.0,
        "regime_bull_pct": 40.0,
        "pattern_score": 51.0,
        "rsi": 59.0,
        "overall_verdict": "WATCH",
        "horizons": {
            "short": {"ml_prob": 40.0, "entry_zone": {"low": 133.72, "high": 140.47}},
            "medium": {"entry_zone": {"low": 133.72, "high": 140.47}},
            "long": {
                "entry_tiers": {
                    "spot_position": {"state": "in_tier", "active_tier_id": "T2"},
                }
            },
        },
    }
    out = enrich_investor_summary_retail_action(inv, 151.21, ticker="SPCX")
    ra = out["retail_action"]

    by_mode = ra["action_title_by_mode"]
    assert "T2" in by_mode["owner"]["title"]
    assert "T2" not in by_mode["scout"]["title"]
    assert "T2" not in by_mode["swing"]["title"]


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
