"""Tests for horizon playbooks (swing, medium, long)."""

from __future__ import annotations

from signals.horizon_playbooks import build_horizon_playbooks, build_long_setup, build_medium_setup
from signals.retail_action_payload import enrich_investor_summary_retail_action


def _full_investor_out() -> dict:
    return {
        "fair_value": 150.0,
        "overall_verdict": "WATCH",
        "regime_bull_pct": 68.0,
        "pattern_score": 55.0,
        "rsi": 42.0,
        "one_answer": {
            "hold_vs_trade": {
                "title": "Hold for years vs take profits",
                "signal_bridge": "Fear in bull market = hold core; trim only extended tactical slice.",
                "long_term": "Stay invested through normal pullbacks when thesis intact.",
                "short_term": "Trim near ST/MT targets; redeploy on pullbacks.",
            },
        },
        "horizons": {
            "short": {
                "ml_prob": 35.0,
                "verdict": "WATCH",
                "entry_zone": {"low": 98.0, "high": 102.0},
                "stop_loss": 94.0,
                "target": 112.0,
            },
            "medium": {
                "ml_prob": 32.0,
                "verdict": "BUY",
                "entry_zone": {"low": 95.0, "high": 100.0},
                "stop_loss": 88.0,
                "target": 125.0,
            },
            "long": {
                "verdict": "BUY",
                "fair_value": 150.0,
                "entry_tiers": {
                    "active_tier_id": "tier2",
                    "target_tier_id": "tier2",
                    "current_assessment": {"label": "Tier 2 MOS", "margin_of_safety_pct": 12.0},
                    "structural_invalidation": {"price": 82.0, "note": "52w floor"},
                    "tiers": [
                        {"id": "tier1", "label": "Tier 1", "low": 105.0, "high": 110.0, "conviction": "Low"},
                        {"id": "tier2", "label": "Tier 2", "low": 92.0, "high": 98.0, "conviction": "Medium"},
                        {"id": "tier3", "label": "Tier 3", "low": 85.0, "high": 90.0, "conviction": "High"},
                    ],
                },
            },
        },
    }


def test_build_horizon_playbooks_all_three():
    inv = _full_investor_out()
    enrich_investor_summary_retail_action(inv, 100.0)
    bundle = build_horizon_playbooks(
        ticker="GOOGL",
        investor_out=inv,
        current_price=100.0,
        response={"high_52w": 115.0},
        market_context={"quadrant": "best_buy_zone", "primary_message": "FEAR IN A BULL MARKET"},
    )
    assert bundle["swing"] is not None
    assert bundle["swing"]["kind"] == "swing"
    assert bundle["medium"] is not None
    assert bundle["medium"]["kind"] == "position_build"
    assert bundle["long"] is not None
    assert bundle["long"]["kind"] == "thesis_tiers"
    assert len(bundle["long"]["tiers"]) >= 2
    assert bundle["long"]["hold_vs_trade"] is not None
    assert bundle["default_primary"] == "short"
    assert bundle["intent_map"]["invest"] == "long"


def test_medium_setup_tranche_sizing():
    inv = _full_investor_out()
    enrich_investor_summary_retail_action(inv, 100.0)
    out = build_medium_setup(ticker="GOOGL", investor_out=inv, current_price=100.0, config={"risk_sizing": {"medium_position_pct": 10.0}})
    assert out is not None
    assert out["trade"]["timeline_weeks"] == "12–26"
    assert out["sizing"] is not None
    assert "Tranche" in out["sizing"]["scale_in"][0]


def test_long_setup_requires_tiers():
    inv = {"horizons": {"long": {"entry_tiers": {"tiers": []}}}}
    assert build_long_setup(ticker="X", investor_out=inv, current_price=100.0) is None
