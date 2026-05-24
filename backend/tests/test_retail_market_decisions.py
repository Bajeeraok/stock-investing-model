"""Tests for retail market decision framework."""
from __future__ import annotations

from signals.retail_market_decisions import build_retail_market_decisions
from signals.ticker_market_context import build_ticker_market_context


def test_five_questions_present():
    out = build_retail_market_decisions(
        macro_regime="Risk-On",
        macro_regime_bundle={"factors": {"vix": 17.0, "hy_oas_bp": 320}},
        market_regime={"market_breadth": "Strong", "participation_narrow": False},
        avg_portfolio_score=62,
        include_p1=False,
    )
    assert len(out["five_questions"]) == 5
    assert out["market_temperature"]["label"]
    assert out["strategy_matrix"]["grid"]["short"] in ("BUY", "HOLD", "REDUCE")
    assert out.get("breadth_panel")


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
