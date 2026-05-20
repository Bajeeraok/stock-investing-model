"""Tests for retail_action_payload — gate tokens and enrichment."""

from __future__ import annotations

from signals.retail_action_payload import (
    build_retail_action_payload,
    enrich_dashboard_signal_row,
    regime_weather_status,
    rsi_status,
    rr_status,
)


def test_rsi_status_hot():
    assert rsi_status(61) == "hot"
    assert rsi_status(49) == "neutral"
    assert rsi_status(30) == "oversold"


def test_regime_weather_stormy():
    assert regime_weather_status(35) == "stormy"
    assert regime_weather_status(65) == "bull"


def test_rr_status_tight():
    assert rr_status(0.43) == "tight"
    assert rr_status(1.2) == "favorable"


def test_build_retail_action_payload_gates_locked():
    p = build_retail_action_payload(
        current_price=103.42,
        fair_value=141.0,
        regime_bull_pct=38.0,
        pattern_score=52.0,
        short_ml_prob=33.0,
        rsi=61.0,
        confidence_mid=48.0,
        overall_verdict="WATCH",
    )
    assert p["gate_cleared"] is False
    assert p["gates_locked_count"] == 2
    assert p["rsi_status"] == "hot"
    assert p["regime_weather_status"] == "stormy"
    assert p["go_no_go"] == "no_go"
    primary = [g for g in p["gates"] if g["id"] in ("valuation", "regime", "momentum", "ml")]
    assert len(primary) == 4
    assert primary[0]["visual_status"] in ("cleared", "blocked", "bull", "stormy", "hot")
    assert "dynamic_subtitle" in p


def test_enrich_dashboard_signal_row():
    row = {
        "ticker": "NOW",
        "close": 103.42,
        "rsi": 61,
        "ml_short_prob": 0.33,
        "confluence_score": 52,
        "plan_action": "WATCH",
        "plan_confidence": 0.48,
        "_global_market_regime": "BEAR",
        "lt_band": {"low": 85, "high": 93},
        "st_band": {"low": 98, "high": 105},
    }
    enrich_dashboard_signal_row(row, regime_bull_pct=38)
    assert row["gate_cleared"] is False
    assert row["rsi_status"] == "hot"
    assert "retail_status" in row
    assert row["retail_status"]["action_title"]
