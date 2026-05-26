"""Tests for retail market decision framework."""
from __future__ import annotations

from signals.retail_market_decisions import build_retail_market_decisions
from signals.ticker_market_context import build_ticker_market_context


def test_five_questions_present():
    out = build_retail_market_decisions(
        macro_regime="Risk-Off",
        global_market_regime="STRONG_BULL",
        macro_regime_bundle={"factors": {"vix": 16.7, "hy_oas_bp": 320}, "hmm_bear_pct_used": 13},
        market_regime={"market_breadth": "Strong", "participation_narrow": False},
        avg_portfolio_score=62,
        include_p1=False,
    )
    assert len(out["five_questions"]) == 5
    assert out.get("market_context")
    assert out["market_context"]["quadrant"] == "best_buy_zone"
    assert out["strategy_matrix"]["grid"]["short"] == "BUY"
    sell_q = next(q for q in out["five_questions"] if "sell" in q["question"].lower())
    assert "No blanket sell today" in sell_q["answer"]
    assert ">20%" in sell_q["answer"]
    assert out["hold_vs_trade"].get("bullets")


def test_holdings_answer_inline():
    out = build_retail_market_decisions(
        portfolio_doctor_v2={
            "sector_allocation": [{"sector": "Technology", "pct": 67.0}],
        },
        retail_briefing={"concentration": {"concentration_pct": 55, "top_positions": []}},
        include_p1=False,
    )
    holdings_q = next(q for q in out["five_questions"] if "right stuff" in q["question"].lower())
    assert "67" in holdings_q["answer"]
    assert "50%" in holdings_q["answer"]
    assert "Portfolio tab" not in holdings_q["answer"]


def test_cpi_if_then_scenarios():
    out = build_retail_market_decisions(
        market_catalysts={
            "scheduled_today": [{"event_type": "CPI", "name": "CPI", "scenario": {"pct_gap_fade": 61}}],
        },
        include_p1=False,
    )
    scenarios = out["if_then_scenarios"]
    assert len(scenarios) >= 3
    assert any("CPI" in s["condition"] for s in scenarios)
    assert scenarios[0].get("gap_fade_note")


def test_credit_warning():
    out = build_retail_market_decisions(
        macro_regime_bundle={"factors": {"hy_oas_bp": 550}},
        include_p1=False,
    )
    assert out["credit_pulse"]["signal"] in ("WARNING", "CAUTION", "DANGER")


def test_p1_sections_without_network():
    out = build_retail_market_decisions(include_p1=False)
    assert "crowd_positioning" not in out or out.get("crowd_positioning") is None


def test_ticker_market_context_earnings():
    md = build_retail_market_decisions(
        market_regime={"market_breadth": "Neutral"},
        include_p1=False,
    )
    ctx = build_ticker_market_context(
        "NVDA",
        sector="Technology",
        score=72,
        regime="UP",
        earnings={"date": "2026-05-20", "days_until": 1},
        is_holding=True,
        market_decisions=md,
    )
    assert ctx["headline"]
    assert ctx["earnings_rule"]["urgency"] == "high"
    assert ctx["horizon_overlay"]["short"]["action"] in ("BUY", "HOLD", "REDUCE")
    assert ctx.get("personal_question")
