"""
Spot-check: 5 synthetic catalyst scenarios → PRIMARY_DRIVER for trading notes.

Run:
  cd backend && python scripts/spotcheck_catalyst_drivers.py
"""
from __future__ import annotations

from signals.catalyst_category_mapper import build_driver_board
from signals.narrative_packet_mapper import to_packet
from signals.narrative_waterfall import (
    Band,
    Gate,
    SignalPacket,
    build_trading_note_payload,
    derive_action_contract,
    derive_catalysts,
    render_plain_trading_notes,
)


def _base(**kwargs) -> SignalPacket:
    defaults = dict(
        ticker="TEST",
        mode="swing",
        asof="2026-08-22",
        spot=100.0,
        trend="UP",
        verdict="WATCH_ZONE",
        score=50,
        gates=[Gate("valuation", False, {"mos_pct": 10.0, "required_pct": 25.0})],
        entry_band=Band(80.0, 90.0),
        stop=75.0,
        invalidation=75.0,
        entry_mode="WAIT",
        hmm_bull_pct=40.0,
        rsi=55.0,
        required_mos_pct=25.0,
        fair_value=120.0,
        unlock_conditions=["Valuation clears"],
    )
    defaults.update(kwargs)
    return SignalPacket(**defaults)


SCENARIOS = [
    (
        "earnings_week",
        _base(
            ticker="NVDA",
            news_events=[{
                "name": "Earnings",
                "event_type": "EARNINGS_CALENDAR",
                "mechanism": "NVDA reports in 4 days — size down into the print",
                "source": "earnings_calendar",
            }],
            rsi=72.0,
        ),
        "BINARY_EVENT",
    ),
    (
        "heavy_insider",
        _base(
            ticker="META",
            driver_context={"insider": {"signal": "selling", "sell_count": 5}},
            rsi=48.0,
        ),
        "SMART_MONEY",
    ),
    (
        "quiet_tape",
        _base(ticker="MSFT", rsi=52.0, hmm_bull_pct=55.0),
        "TECHNICAL",
    ),
    (
        "dxy_sensitive",
        _base(
            ticker="GLD",
            mode="scout",
            unlock_conditions=[],
            sensitivities=["USD-sensitive"],
            news_events=[{
                "name": "Dollar spike",
                "mechanism": "DXY surge pressures risk assets",
                "source": "headline",
                "age_hours": 3,
            }],
        ),
        "CROSS_ASSET",
    ),
    (
        "geopolitical_headline",
        _base(
            ticker="XOM",
            mode="owner",
            news_events=[{
                "name": "Tariffs",
                "mechanism": "Tariff escalation and sanctions risk oil flow",
                "source": "headline",
                "age_hours": 6,
            }],
            driver_context={"macro": {"cpi_yoy": 2.8}},
        ),
        "GEOPOLITICAL",
    ),
]


def _run_one(name: str, pkt: SignalPacket, expected: str) -> bool:
    cats = derive_catalysts(pkt)
    board = build_driver_board(pkt, cats, mode=pkt.mode)
    primary = board["primary_driver"]["category"]
    payload = build_trading_note_payload(pkt, derive_action_contract(pkt), cats)
    notes = render_plain_trading_notes(pkt, derive_action_contract(pkt), cats)
    ok = primary == expected
    mark = "OK" if ok else "FAIL"
    print(f"[{mark}] {name}: got {primary} (want {expected}) chip={board.get('chip_label')}")
    print(f"       headline: {board['primary_driver']['headline'][:90]}")
    print(f"       DRIVER_CATEGORY={payload.get('DRIVER_CATEGORY')}")
    for ln in notes.splitlines():
        print(f"       {ln}")
    return ok


def _run_earnings_via_detail() -> bool:
    detail = {
        "ticker": "AAPL",
        "current_price": 190.0,
        "rsi": 60,
        "earnings": {"days_until": 5, "date": "2026-08-27"},
        "investor_summary": {
            "retail_action": {"gates": [], "assessment_pct": 12},
            "horizons": {},
            "regime_bull_pct": 50,
            "pattern_score": 50,
            "fair_value": 210,
            "trade_roadmap": {
                "news_sentiment_layer": {
                    "catalyst_cards": [],
                    "headlines": [{"title": "Quiet session for megacaps"}],
                }
            },
        },
        "confidence": {"confidence": 0.55},
    }
    try:
        pkt = to_packet(detail, "swing")
    except Exception as e:
        print(f"[FAIL] earnings_via_detail: to_packet error {e}")
        return False
    types = [e.get("event_type") for e in (pkt.news_events or [])]
    ok = any(t in ("EARNINGS_CALENDAR", "EARNINGS") for t in types if t)
    # Also accept mechanism text when event_type is missing from fallback card
    if not ok:
        blob = " ".join(
            str(e.get("mechanism") or e.get("title") or "") for e in (pkt.news_events or [])
        ).lower()
        ok = "earnings" in blob
    mark = "OK" if ok else "FAIL"
    print(f"[{mark}] earnings_via_detail: news event_types={types}")
    return ok


def main() -> int:
    print("=== Catalyst driver spot-check (5 scenarios + earnings inject) ===")
    ok = True
    for name, pkt, expected in SCENARIOS:
        ok = _run_one(name, pkt, expected) and ok
        print()
    ok = _run_earnings_via_detail() and ok
    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
