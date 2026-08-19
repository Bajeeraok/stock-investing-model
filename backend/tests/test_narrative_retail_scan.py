"""Starter vs MOS unlock, sector-keyed gold catalysts, retail 10-second scan."""

from __future__ import annotations

from signals.narrative_packet_mapper import to_packet
from signals.narrative_waterfall import (
    Band,
    Catalyst,
    Gate,
    SignalPacket,
    band_clears_full_mos,
    build_summary,
    derive_catalysts,
    example_packet_amzn,
    retail_scan_banned_hits,
    validate_catalysts,
)


def _amd_like(**kwargs) -> SignalPacket:
    """AMD swing snapshot: rich vs FV, nearby MA50 band, hard lock at spot."""
    defaults = dict(
        ticker="AMD",
        mode="swing",
        asof="2026-08-18",
        spot=514.39,
        trend="UP",
        verdict="WAIT",
        score=72,
        gates=[
            Gate("valuation", False, {"mos_pct": -7.6, "required_pct": 25.0, "text": "Rich"}),
            Gate("market_weather", True, {"hmm_bull_pct": 70.0, "need_pct": 60.0, "tape": "Bull"}),
            Gate("momentum_chop", False, {"rsi": 62.0}),
            Gate("ml_probability", True, {"ml_prob_pct": 35.0, "threshold_pct": 25.0}),
            Gate("confidence", True, {"conf_pct": 55.0}),
        ],
        entry_band=Band(495.0, 511.0),
        stop=479.78,
        invalidation=479.78,
        target=625.88,
        rr=3.22,
        entry_mode="WAIT",
        max_tranche_pct=0.0,
        sector="Technology",
        fair_value=475.0,
        mos_pct=-7.6,
        required_mos_pct=25.0,
        full_size_price=380.0,
        hmm_bull_pct=70.0,
        rsi=62.0,
        unlock_conditions=["Valuation clears", "Momentum Chop clears"],
        sensitivities=["gold-sensitive", "USD-sensitive", "volatility-sensitive"],
    )
    defaults.update(kwargs)
    return SignalPacket(**defaults)


def test_nearby_band_does_not_clear_full_mos():
    p = _amd_like()
    assert not band_clears_full_mos(p)
    mos_at_band = (p.fair_value - p.entry_band.hi) / p.entry_band.hi * 100
    assert mos_at_band < p.required_mos_pct


def test_valuation_catalyst_is_starter_not_mos_unlock():
    p = _amd_like()
    cats = derive_catalysts(p)
    assert validate_catalysts(p, cats) == []
    val = [c for c in cats if c.direction == "unlocks" and "starter" in (c.name + c.mechanism).lower()]
    assert val, f"expected a starter-watch unlock, got {[c.name for c in cats]}"
    for c in cats:
        if c.direction != "unlocks":
            continue
        mech = c.mechanism.lower()
        assert "margin of safety" not in mech
        assert "restores the required" not in mech
        assert "true entry" not in mech


def test_safe_haven_catalyst_cannot_attach_to_technology():
    p = _amd_like()
    cats = derive_catalysts(p)
    names = {c.name for c in cats}
    assert "Safe-haven outflow" not in names
    assert validate_catalysts(p, cats) == []
    # Assertion the user asked for: even a leaked catalyst is rejected.
    leaked = Catalyst(
        "Safe-haven outflow",
        "breaks",
        "Geopolitical de-escalation rotates capital out of defensive assets.",
        "risk-on",
        "days",
    )
    errs = validate_catalysts(p, [leaked])
    assert errs and "Technology" in errs[0]


def test_safe_haven_catalyst_attaches_to_gld():
    p = _amd_like(
        ticker="GLD",
        sector="Basic Materials",
        sensitivities=["gold-sensitive"],
        gates=[
            Gate("valuation", True, {"mos_pct": 8.0, "required_pct": 10.0}),
            Gate("market_weather", True, {"hmm_bull_pct": 40.0, "need_pct": 60.0}),
            Gate("momentum_chop", True, {"rsi": 48.0}),
            Gate("ml_probability", True, {"ml_prob_pct": 30.0, "threshold_pct": 25.0}),
        ],
        unlock_conditions=[],
        entry_mode="FULL",
        rsi=48.0,
    )
    cats = derive_catalysts(p)
    assert any(c.name == "Safe-haven outflow" for c in cats)
    assert validate_catalysts(p, cats) == []


def test_retail_scan_answers_buy_today_price_and_give_up():
    out = build_summary(_amd_like(), llm=None)
    assert out["status"] == "ok"
    scan = out["retail_scan"]
    text = scan["text"]
    assert "WAIT" in scan["headline"]
    assert "don't buy today" in scan["headline"].lower()
    # Headline is why-wait, not an RSI print.
    assert not any(ch.isdigit() for ch in scan["headline"])
    assert "ran up too fast" in scan["reason"].lower()
    assert scan["starter_only_zone"] is True
    buy = scan["lines"][0]
    assert "495" in buy and "511" in buy
    assert "starter only" in buy.lower()
    assert "not full size" in buy.lower()
    assert any("never chase" in ln.lower() and "511" in ln for ln in scan["lines"])
    assert any("walk away" in ln.lower() and "479.78" in ln for ln in scan["lines"])
    assert any("625" in ln for ln in scan["lines"])
    assert "days to a few weeks" in scan["timing"].lower()
    assert retail_scan_banned_hits(text) == []
    # Cover-the-prose: five lines answer the three questions.
    assert len(scan["lines"]) <= 4


def test_full_size_price_lives_in_why_not_as_mos_unlock():
    out = build_summary(_amd_like(), llm=None)
    why = " ".join(out["why"]).lower()
    assert "380" in why or "starter" in why
    assert "restores the required" not in why
    assert "margin of safety" not in " ".join(
        c["mechanism"] for c in out["catalysts"] if c["direction"] == "unlocks"
    ).lower()


def test_example_packet_retail_scan_has_no_banned_vocab():
    out = build_summary(example_packet_amzn(), llm=None)
    assert out["status"] == "ok"
    assert retail_scan_banned_hits(out["retail_scan"]["text"]) == []


def test_to_packet_copies_sector_and_does_not_attach_gold_to_amd():
    detail = {
        "ticker": "AMD",
        "current_price": 514.39,
        "rsi": 62,
        "sector": "Technology",
        "investor_summary": {
            "fair_value": 475.0,
            "pattern_score": 80,
            "regime_bull_pct": 70,
            "retail_action": {
                "entry_mode": "hard_lock",
                "assessment_pct": -7.6,
                "action_title": "WAIT",
                "max_sizing_pct": 0,
                "gates": [
                    {"id": "valuation", "pass": False, "detail": "Rich vs fair value"},
                    {"id": "momentum", "pass": False, "detail": "hot"},
                    {"id": "regime", "pass": True, "detail": "ok"},
                    {"id": "ml", "pass": True, "detail": "ok"},
                ],
            },
            "horizons": {
                "medium": {
                    "entry_zone": {"low": 495.0, "high": 511.0, "levels": []},
                    "stop_loss": 479.78,
                    "target": 625.88,
                    "ml_prob": 30,
                }
            },
        },
        "confidence": {
            "confidence": 0.55,
            "hmm": {},
            "options": {},
            "nlp": {},
            "ml_horizons": {},
        },
        "cross_asset": {
            "badges": ["gold-sensitive", "USD-sensitive", "volatility-sensitive"],
        },
    }
    pkt = to_packet(detail, "swing")
    assert pkt.sector == "Technology"
    assert pkt.required_mos_pct == 25.0
    assert pkt.full_size_price == 380.0
    cats = derive_catalysts(pkt)
    assert not any(c.name == "Safe-haven outflow" for c in cats)
    assert validate_catalysts(pkt, cats) == []
    out = build_summary(pkt, llm=None)
    assert out["status"] == "ok"
    assert out["retail_scan"]["starter_only_zone"] is True


def test_trading_notes_come_with_summary_without_llm():
    out = build_summary(_amd_like(), llm=None)
    notes = out["trading_notes"]
    assert notes
    assert "don't buy today" in notes.lower() or "wait" in notes.lower()
    from signals.narrative_waterfall import layer3_banned_hits
    assert layer3_banned_hits(notes) == []


def test_layer3_banned_hits_flags_quant_recap():
    from signals.narrative_waterfall import layer3_banned_hits
    blob = (
        "BlackRock trades at a 14.2% margin of safety in a bull tape "
        "with HMM conviction — that confluence is the true entry."
    )
    hits = layer3_banned_hits(blob)
    assert "margin of safety" in hits
    assert "tape" in hits
    assert "hmm" in hits
    assert "confluence" in hits


def test_layer3_retries_jargon_then_accepts_plain():
    from signals.narrative_waterfall import (
        NarrativeEngine,
        derive_action_contract,
        derive_catalysts,
        example_packet_amzn,
        render_retail_scan,
    )
    p = example_packet_amzn()
    calls = {"n": 0}

    def llm(_sys: str, _user: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return (
                "AMZN has a 30.4% margin of safety on a bull tape. "
                "HMM is 97%."
            )
        return (
            "Do not add a full position today. Price ran up too fast.\n\n"
            "A small first slice only if it pulls into $245.14-$257.52 after it cools off.\n\n"
            "Walk away if it closes below $232.76.\n\n"
            "Watch for a calmer pullback over 1-2 weeks."
        )

    eng = NarrativeEngine(llm)
    contract = derive_action_contract(p)
    cats = derive_catalysts(p)
    scan = render_retail_scan(p, contract)
    text, status = eng.generate(p, contract, cats, retail_scan=scan)
    assert status == "ok"
    assert calls["n"] >= 2
    assert "margin of safety" not in text.lower()
    assert "hmm" not in text.lower()
