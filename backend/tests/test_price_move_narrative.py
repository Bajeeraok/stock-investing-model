"""Tests for signals.price_move_narrative — rule-based 'why is this stock moving' text."""

from __future__ import annotations

from signals.price_move_narrative import build_price_move_narrative


def test_stock_specific_catalyst_wins_even_with_market_comove():
    out = build_price_move_narrative(
        ticker="XYZ",
        day_change_pct=-6.0,
        spy_day_change_pct=-0.8,
        catalyst={
            "active": True,
            "top_event_type": "GUIDANCE_CUT",
            "headline_summary": "XYZ cuts full-year guidance on soft demand",
            "override_note": "Catalyst active (guidance cut, 3h ago) — negative event may override bullish technicals.",
            "hours_since_catalyst": 3.0,
        },
    )
    assert out["driver"] == "stock_specific"
    assert "guidance cut" in out["headline"].lower()
    assert out["citation"] is not None


def test_recent_earnings_flagged_without_other_catalyst():
    out = build_price_move_narrative(
        ticker="ABC",
        day_change_pct=4.5,
        spy_day_change_pct=0.1,
        catalyst=None,
        earnings_days_since=1,
    )
    assert out["driver"] == "earnings"
    assert "earnings report" in out["headline"].lower()


def test_broad_market_comove_down():
    out = build_price_move_narrative(
        ticker="AAPL",
        day_change_pct=-1.8,
        spy_day_change_pct=-1.5,
        global_market_regime="BEAR",
        catalyst=None,
    )
    assert out["driver"] == "broad_market"
    assert "broader market" in out["headline"].lower()
    assert "risk-off" in (out["detail"] or "").lower()


def test_broad_market_comove_requires_same_direction():
    # SPY down but ticker up — not a co-move, should not be classified as broad_market
    out = build_price_move_narrative(
        ticker="AAPL",
        day_change_pct=2.0,
        spy_day_change_pct=-1.5,
        catalyst=None,
    )
    assert out["driver"] != "broad_market"


def test_idiosyncratic_move_with_no_catalyst_is_unclear_not_fabricated():
    out = build_price_move_narrative(
        ticker="QRS",
        day_change_pct=-7.0,
        spy_day_change_pct=0.1,
        catalyst=None,
    )
    assert out["driver"] == "unclear"
    assert "without a clear" in out["headline"].lower() or "no dominant" in out["headline"].lower()


def test_no_data_does_not_crash():
    out = build_price_move_narrative(ticker=None, day_change_pct=None, spy_day_change_pct=None)
    assert out["driver"] == "unclear"
    assert isinstance(out["headline"], str) and out["headline"]


def test_unclear_case_gets_volume_and_rsi_color():
    out = build_price_move_narrative(
        ticker="QRS",
        day_change_pct=-7.0,
        spy_day_change_pct=0.1,
        catalyst=None,
        volume_ratio=2.4,
        rsi=76.0,
    )
    assert out["driver"] == "unclear"
    assert "2.4x average" in out["detail"]
    assert "overbought" in out["detail"]


def test_unclear_case_stays_none_without_notable_volume_or_rsi():
    # Near-1x volume and mid-range RSI aren't worth a sentence — detail should stay empty.
    out = build_price_move_narrative(
        ticker="QRS",
        day_change_pct=-1.0,
        spy_day_change_pct=0.1,
        catalyst=None,
        volume_ratio=1.05,
        rsi=50.0,
    )
    assert out["detail"] is None


def test_stock_specific_catalyst_detail_includes_volume_when_notable():
    out = build_price_move_narrative(
        ticker="XYZ",
        day_change_pct=-6.0,
        spy_day_change_pct=-0.8,
        catalyst={
            "active": True,
            "top_event_type": "GUIDANCE_CUT",
            "headline_summary": "XYZ cuts full-year guidance on soft demand",
            "override_note": "Catalyst active (guidance cut, 3h ago) — negative event may override bullish technicals.",
            "hours_since_catalyst": 3.0,
        },
        volume_ratio=3.1,
    )
    assert "soft demand" in out["detail"]
    assert "3.1x average" in out["detail"]
