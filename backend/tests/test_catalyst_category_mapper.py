"""Catalyst Translation Matrix — 6-category classify + PRIMARY_DRIVER ranking."""

from __future__ import annotations

from signals.catalyst_category_mapper import (
    build_driver_board,
    classify_text,
    map_catalyst_like,
    primary_driver_plain,
)
from signals.narrative_waterfall import (
    Band,
    Gate,
    SignalPacket,
    build_trading_note_payload,
    derive_action_contract,
    derive_catalysts,
    render_plain_trading_notes,
)


def test_classify_text_six_categories():
    assert classify_text("CPI prints hot; sticky inflation") == "MACRO_RATES"
    assert classify_text("tariff escalation and sanctions") == "GEOPOLITICAL"
    assert classify_text("DXY surge pressures risk assets") == "CROSS_ASSET"
    assert classify_text("earnings in 5 days") == "BINARY_EVENT"
    assert classify_text("insider selling accelerated") == "SMART_MONEY"
    assert classify_text("RSI overbought breakdown") == "TECHNICAL"
    assert classify_text("random chatter") == "TECHNICAL"


def test_event_type_overrides_keywords():
    assert classify_text("soft tape", event_type="EARNINGS_CALENDAR") == "BINARY_EVENT"
    assert classify_text("anything", event_type="FOMC") == "MACRO_RATES"


def test_binary_beats_technical_for_primary_driver():
    pkt = SignalPacket(
        ticker="NVDA",
        mode="swing",
        asof="2026-08-20",
        spot=120.0,
        trend="DOWN",
        verdict="WATCH_ZONE",
        score=40,
        gates=[
            Gate("valuation", False, {"mos_pct": 10.0, "required_pct": 25.0}),
            Gate("market_weather", False, {"need_pct": 60.0, "hmm_bull_pct": 0.0, "tape": "Mixed"}),
            Gate("momentum_chop", False, {"rsi": 72.0}),
        ],
        entry_band=Band(90.75, 109.61),
        stop=85.30,
        invalidation=85.30,
        entry_mode="WAIT",
        hmm_bull_pct=0.0,
        rsi=72.0,
        required_mos_pct=25.0,
        fair_value=140.0,
        unlock_conditions=[
            "Valuation clears",
            "Market Weather clears",
            "Momentum Chop clears",
        ],
        news_events=[
            {
                "name": "earnings date (known event)",
                "event_type": "EARNINGS_CALENDAR",
                "direction": "neutral",
                "mechanism": "NVDA reports in 9 days — size down into the print",
                "watch": "size down into the print",
                "horizon": "days",
            }
        ],
    )
    cats = derive_catalysts(pkt)
    board = build_driver_board(pkt, cats)
    assert board["primary_driver"]["category"] == "BINARY_EVENT"
    assert "9 days" in board["primary_driver"]["headline"].lower() or "reports" in board[
        "primary_driver"
    ]["headline"].lower()

    payload = build_trading_note_payload(pkt, derive_action_contract(pkt), cats)
    assert payload["DRIVER_CATEGORY"] == "BINARY_EVENT"
    assert payload["BINARY_EVENT"] != "NONE"

    notes = render_plain_trading_notes(pkt, derive_action_contract(pkt), cats).lower()
    assert "earnings" in notes or "9 days" in notes or "reports" in notes
    assert "rsi" not in notes
    assert "hmm" not in notes


def test_insider_context_outranks_technical_when_no_news():
    pkt = SignalPacket(
        ticker="XYZ",
        mode="swing",
        asof="2026-08-20",
        spot=50.0,
        trend="UP",
        verdict="WATCH_ZONE",
        score=55,
        gates=[Gate("valuation", True, {})],
        entry_band=Band(40.0, 45.0),
        stop=38.0,
        invalidation=38.0,
        entry_mode="WAIT",
        hmm_bull_pct=55.0,
        rsi=68.0,
        unlock_conditions=[],
        driver_context={"insider": {"signal": "selling", "sell_count": 4}},
    )
    board = build_driver_board(pkt, [])
    assert board["primary_driver"]["category"] == "SMART_MONEY"
    plain = primary_driver_plain(board)
    assert "institutional" in plain.lower() or "insider" in plain.lower()


def test_map_catalyst_boosts_near_earnings():
    near = map_catalyst_like(mechanism="Reports in 3 days", event_type="EARNINGS")
    far = map_catalyst_like(mechanism="Reports in 40 days", event_type="EARNINGS")
    assert near.score > far.score
