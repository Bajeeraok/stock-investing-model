"""Tests for pre-market market catalyst board (P0)."""
from __future__ import annotations

import datetime as dt

from signals.market_catalysts import build_market_catalysts


def test_scheduled_today_filters_us_high_impact():
    today = dt.date(2026, 5, 21)
    cal = [
        {"date": "2026-05-21", "name": "Consumer Price Index (CPI)", "country": "US"},
        {"date": "2026-05-21", "name": "ECB Rate Decision", "country": "EU"},
        {"date": "2026-05-22", "name": "FOMC Minutes", "country": "US"},
    ]
    out = build_market_catalysts(
        premarket={"composite_score": 0.1, "bias": "SLIGHT BULL", "signals": []},
        economic_calendar=cal,
        today=today,
    )
    assert len(out["scheduled_today"]) == 1
    assert out["scheduled_today"][0]["event_type"] == "CPI"


def test_tension_pm_bull_regime_bear():
    out = build_market_catalysts(
        premarket={"composite_score": 0.25, "bias": "BULL", "signals": []},
        spy_regime="DOWN",
        economic_calendar=[],
        today=dt.date(2026, 5, 21),
    )
    codes = [t["code"] for t in out["tensions"]]
    assert "pm_bull_regime_bear" in codes


def test_live_tape_from_signals():
    out = build_market_catalysts(
        premarket={
            "composite_score": 0.2,
            "bias": "BULL",
            "signals": [
                {"name": "S&P 500 Futures (ES=F)", "score": 0.5, "raw_value": "+0.40%", "direction": "Bullish"},
                {"name": "VIX", "score": 0.05, "raw_value": "18.0", "direction": "Neutral"},
            ],
        },
        economic_calendar=[],
        today=dt.date(2026, 5, 21),
    )
    assert len(out["live_tape"]) == 1
    assert "ES" in out["live_tape"][0]["name"] or "S&P" in out["live_tape"][0]["name"]


def test_flip_narratives_default_when_no_events():
    out = build_market_catalysts(premarket={"composite_score": 0, "bias": "NEUTRAL", "signals": []}, today=dt.date(2026, 5, 21))
    assert len(out["flip_narratives"]) >= 1
    assert out["flip_narratives"][0]["event_type"] == "Tape"


def test_morning_newsletter_includes_catalyst_section():
    from signals.morning_newsletter import build_morning_newsletter

    nl = build_morning_newsletter(
        premarket_report={
            "bias": "BULL",
            "composite_score": 0.2,
            "signals": [],
            "market_catalysts": {
                "summary_line": "Pre-market BULL · 1 macro catalyst(s) today",
                "scheduled_today": [{"name": "CPI", "event_type": "CPI", "time_et": "08:30"}],
                "tensions": [{"level": "High", "code": "macro_event_gap", "message": "Macro release today."}],
            },
        },
    )
    titles = [s["title"] for s in nl.get("sections") or []]
    assert "Market catalysts" in titles
