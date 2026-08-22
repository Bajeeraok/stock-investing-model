# -*- coding: utf-8 -*-
from pathlib import Path

# --- tests ---
test_path = Path(__file__).resolve().parent.parent / "tests" / "test_narrative_retail_scan.py"
test_path.write_text(
    '''"""Trading notes: 3-bullet execution format, plain English, no RSI/HMM jargon."""

from __future__ import annotations

from signals.narrative_waterfall import (
    Band,
    Gate,
    SignalPacket,
    build_summary,
    build_trading_note_payload,
    derive_action_contract,
    derive_catalysts,
    example_packet_amzn,
    layer3_banned_hits,
    map_execution_mode,
    render_plain_trading_notes,
    trading_note_structure_errors,
)


def test_plain_notes_are_three_bullets_with_status_emoji():
    pkt = example_packet_amzn()
    out = build_summary(pkt, llm=None)
    notes = out["trading_notes"]
    lines = [ln for ln in notes.splitlines() if ln.strip()]
    assert len(lines) == 3
    assert lines[0].lstrip("•-* ").startswith(("🛑", "🚦", "🟢"))
    assert "ACTION:" in lines[0]
    assert "CATALYST" in lines[1].upper() or "DRIVER" in lines[1].upper()
    assert layer3_banned_hits(notes) == []
    assert "rsi" not in notes.lower()
    assert "hmm" not in notes.lower()
    assert "institutions" not in notes.lower()
    assert trading_note_structure_errors(notes) == []


def test_execution_payload_maps_modes_and_actions():
    assert map_execution_mode("scout") == "DAY_TRADING"
    assert map_execution_mode("swing") == "SWING_TRADING"
    assert map_execution_mode("owner") == "LONG_TERM_INVESTOR"
    pkt = example_packet_amzn()
    contract = derive_action_contract(pkt)
    payload = build_trading_note_payload(pkt, contract, derive_catalysts(pkt))
    assert payload["TICKER"] == "AMZN"
    assert payload["MODE"] == "SWING_TRADING"
    assert payload["PRIMARY_ACTION"] in {"AVOID", "WAIT_PULLBACK", "BUY_STARTER", "CONFIRMED_BUY"}
    assert payload["STATUS_EMOJI"] in {"🛑", "🚦", "🟢"}
    assert payload["BUY_ZONE"]
    assert payload["STOP_LOSS"]


def test_layer3_banned_hits_flags_quant_and_fake_institutions():
    blob = (
        "BlackRock trades at a 14.2% margin of safety in a bull tape "
        "with HMM conviction — that confluence is the true entry. "
        "0% bull conditions until institutions are buying."
    )
    hits = layer3_banned_hits(blob)
    assert "margin of safety" in hits
    assert "tape" in hits
    assert "hmm" in hits
    assert "confluence" in hits
    assert "bull conditions" in hits
    assert "institutions are buying" in hits


def test_trading_notes_surface_known_event_catalyst():
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
            Gate("momentum_chop", False, {"rsi": 62.0}),
        ],
        entry_band=Band(90.75, 109.61),
        stop=85.30,
        invalidation=85.30,
        entry_mode="STARTER_ONLY",
        hmm_bull_pct=0.0,
        rsi=62.0,
        required_mos_pct=25.0,
        fair_value=140.0,
        unlock_conditions=[
            "Valuation clears",
            "Market Weather clears",
            "Momentum Chop clears",
        ],
        news_events=[{
            "name": "earnings date (known event)",
            "event_type": "EARNINGS_CALENDAR",
            "direction": "neutral",
            "mechanism": "NVDA reports in 9 days — size down into the print",
            "watch": "size down into the print",
            "horizon": "days",
        }],
    )
    cats = derive_catalysts(pkt)
    assert cats[0].mechanism.startswith("Known event:") or cats[0].mechanism.startswith("Known event:")
    assert not any("HMM" in c.mechanism or "RSI" in c.mechanism for c in cats)

    notes = render_plain_trading_notes(pkt, derive_action_contract(pkt), cats)
    low = notes.lower()
    assert "9 days" in low or "earnings" in low or "reports" in low
    assert "rsi" not in low
    assert "hmm" not in low
    assert layer3_banned_hits(notes) == []
    assert len([ln for ln in notes.splitlines() if ln.strip()]) == 3


def test_mapper_news_cards_reach_trading_notes():
    from signals.narrative_packet_mapper import to_packet

    detail = {
        "ticker": "NVDA",
        "current_price": 120.0,
        "rsi": 55.0,
        "sector": "Technology",
        "investor_summary": {
            "regime_bull_pct": 40.0,
            "pattern_score": 50,
            "fair_value": 140.0,
            "retail_action": {
                "action_title": "WAIT",
                "max_sizing_pct": 0.0,
                "assessment_pct": 10.0,
                "gates": [
                    {"id": "valuation", "pass": False},
                    {"id": "regime", "pass": False},
                    {"id": "momentum", "pass": False},
                ],
            },
            "horizons": {
                "medium": {
                    "entry_zone": {"low": 90.0, "high": 110.0},
                    "target": 150.0,
                    "stop_loss": 85.0,
                }
            },
            "trade_roadmap": {
                "news_sentiment_layer": {
                    "catalyst_cards": [{
                        "name": "guidance raise",
                        "event_type": "GUIDANCE_RAISE",
                        "direction": "bullish",
                        "mechanism": "NVDA raised full-year outlook on AI demand",
                        "watch": "estimate revisions",
                        "horizon": "days",
                    }],
                }
            },
            "valuation_deck": {"street": {}},
        },
        "confidence": {
            "confidence": 0.5,
            "hmm": {},
            "options": {},
            "nlp": {"sentiment_label": "BULLISH"},
            "ml_horizons": {},
        },
        "cross_asset": {"badges": []},
    }
    pkt = to_packet(detail, "swing")
    assert pkt.news_events
    assert "raised full-year outlook" in (pkt.news_events[0].get("mechanism") or "")
    cats = derive_catalysts(pkt)
    assert any(c.mechanism.startswith("News:") for c in cats)
    notes = build_summary(pkt, llm=None)["trading_notes"].lower()
    assert "raised full-year outlook" in notes or "outlook" in notes
'''
    ,
    encoding="utf-8",
)
print("wrote tests")

# --- UI card ---
ui = Path(__file__).resolve().parents[2] / "web" / "components" / "dashboard" / "tickerDetail" / "NarrativeWaterfallCard.tsx"
ut = ui.read_text(encoding="utf-8")
old = '''  const notes = (data?.trading_notes || data?.narrative || "").trim();
  const noteParagraphs = notes
    ? notes.split(/\\n\\s*\\n/).map((p) => p.trim()).filter(Boolean)
    : [];
'''
new = '''  const notes = (data?.trading_notes || data?.narrative || "").trim();
  // Prefer single-newline bullets (execution-note format); fall back to paragraph splits.
  const noteParagraphs = notes
    ? (notes.includes("\\n")
        ? notes.split(/\\n/).map((p) => p.trim()).filter(Boolean)
        : notes.split(/\\n\\s*\\n/).map((p) => p.trim()).filter(Boolean))
    : [];
'''
if old not in ut:
    # try alternate quote styles
    if "noteParagraphs" not in ut:
        raise SystemExit("UI noteParagraphs not found")
    ut2 = ut.replace(
        "notes.split(/\\n\\s*\\n/)",
        '(notes.includes("\\n") ? notes.split(/\\n/) : notes.split(/\\n\\s*\\n/))',
        1,
    )
    if ut2 == ut:
        raise SystemExit("UI replace failed")
    ut = ut2
else:
    ut = ut.replace(old, new, 1)

ut = ut.replace(
    'description="Verdict first, then the four numbers that matter. Why opens trading notes, then the model checks."',
    'description="Verdict first, then the four numbers that matter. Trading notes are a 10-second execution scan (3 bullets)."',
    1,
)
ui.write_text(ut, encoding="utf-8")
print("patched UI", ui)
