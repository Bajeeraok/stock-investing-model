"""Morning newsletter — reconciled quadrant alignment and copy quality."""

from __future__ import annotations

from signals.market_context_reconciler import reconcile_market_context
from signals.morning_newsletter import build_morning_newsletter, _human_et_timestamp


def _best_buy_context() -> dict:
    return reconcile_market_context(
        temperature={"level": "cold", "label": "COOL", "vix": 19.5},
        macro_regime="Risk-Off",
        global_market_regime="STRONG_BULL",
        macro_regime_bundle={"hmm_bear_pct_used": 4.6},
    )


def test_human_et_timestamp():
    s = _human_et_timestamp("2026-05-25T22:08:13-04:00")
    assert "May 25, 2026" in s
    assert "10:08 PM ET" in s
    assert "2026-05-25T" not in s


def test_newsletter_best_buy_zone_aligns_with_hero():
    ctx = _best_buy_context()
    nl = build_morning_newsletter(
        as_of_date="2026-05-25T22:08:13-04:00",
        macro_regime="Risk-Off",
        market_context=ctx,
        trim_candidates=[{"ticker": "MSFT"}, {"ticker": "META"}],
        earnings_risk_count=5,
        trigger_levels={"levels": {"SPY": {"primary_trigger": 732.0}}},
        hold_vs_trade={
            "headline": "Long-term hold vs tactical trim?",
            "answer": "Core thesis names vs swing trades — different rules apply in a fear-in-bull setup.",
            "bullets": [
                "Core thesis names (5–10 yr): hold through fear if thesis intact.",
                "Tactical trades: buy dips with stops; trim only if up >20% or thesis breaks.",
            ],
        },
    )
    assert nl["quadrant"] == "best_buy_zone"
    assert "YOLO" not in nl["headline"].upper()
    assert "YOLO" not in " ".join(nl["three_line_brief"]).upper()
    assert "YOLO" not in " ".join(nl["action_items"]).upper()

    pulse = next(s for s in nl["sections"] if s["title"] == "Market pulse")
    assert "YOLO" not in " ".join(pulse["items"]).upper()
    assert "FEAR IN A BULL MARKET" in pulse["items"][0].upper() or "Unified read" in pulse["items"][0]

    line1 = nl["three_line_brief"][0]
    assert "Setup" in line1
    assert "Fear in bull market" in line1.lower() or "fear" in line1.lower()
    assert "Risk-Off" not in line1 or "fear" in line1.lower()

    line2 = nl["three_line_brief"][1]
    assert "MSFT" in line2 and "META" in line2

    line3 = nl["three_line_brief"][2]
    assert "732" in line3
    assert "holds = add" in line3.lower()

    assert "10:08 PM ET" in nl["headline"]
    assert "open any ticker" not in (nl.get("hold_vs_trade_teaser") or "").lower()


def test_newsletter_fallback_no_yolo_on_risk_off():
    nl = build_morning_newsletter(macro_regime="Risk-Off")
    joined = " ".join(nl["three_line_brief"] + nl["action_items"]).upper()
    assert "YOLO" not in joined
    assert "SPECULATIVE" in joined or "AVOID" in joined
