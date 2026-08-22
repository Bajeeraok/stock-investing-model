"""Trading notes must lead with real-world catalysts, not RSI/HMM jargon."""

from __future__ import annotations

from signals.narrative_waterfall import (
    Band,
    Gate,
    SignalPacket,
    build_summary,
    derive_catalysts,
    example_packet_amzn,
    layer3_banned_hits,
)


def test_plain_notes_state_when_no_company_catalyst():
    out = build_summary(example_packet_amzn(), llm=None)
    notes = out["trading_notes"].lower()
    assert "no fresh company catalyst" in notes
    assert layer3_banned_hits(out["trading_notes"]) == []
    assert "rsi" not in notes
    assert "hmm" not in notes
    assert "institutions" not in notes


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


def test_trading_notes_lead_with_known_event_catalyst():
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
    assert cats[0].mechanism.startswith("Known event:")
    assert not any("HMM" in c.mechanism or "RSI" in c.mechanism for c in cats)

    notes = build_summary(pkt, llm=None)["trading_notes"]
    low = notes.lower()
    assert "reports in 9 days" in low
    assert "known event" in low or "earnings" in low
    assert "no fresh company catalyst" not in low
    assert "institutions" not in low
    assert "rsi" not in low
    assert layer3_banned_hits(notes) == []


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
    assert "raised full-year outlook" in notes
    assert "no fresh company catalyst" not in notes
