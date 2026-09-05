"""Tests for retail_action_payload — gate tokens and enrichment."""

from __future__ import annotations

from signals.retail_action_payload import (
    _price_anchor_clause,
    build_retail_action_payload,
    build_trading_gates,
    enrich_dashboard_signal_row,
    regime_weather_status,
    rsi_status,
    rr_status,
)


def test_rsi_status_hot():
    assert rsi_status(61) == "hot"
    assert rsi_status(49) == "neutral"
    assert rsi_status(30) == "oversold"


def test_regime_weather_stormy():
    assert regime_weather_status(35) == "stormy"
    assert regime_weather_status(65) == "bull"


def test_rr_status_tight():
    assert rr_status(0.43) == "tight"
    assert rr_status(1.2) == "favorable"


def test_build_retail_action_payload_gates_locked():
    p = build_retail_action_payload(
        current_price=103.42,
        fair_value=141.0,
        regime_bull_pct=38.0,
        pattern_score=52.0,
        short_ml_prob=33.0,
        rsi=61.0,
        confidence_mid=48.0,
        overall_verdict="WATCH",
    )
    assert p["gate_cleared"] is False
    assert p["gates_locked_count"] == 2
    assert p["rsi_status"] == "hot"
    assert p["regime_weather_status"] == "stormy"
    assert p["go_no_go"] == "no_go"
    primary = [g for g in p["gates"] if g["id"] in ("valuation", "regime", "momentum", "ml")]
    assert len(primary) == 4
    assert primary[0]["visual_status"] in ("cleared", "blocked", "bull", "stormy", "hot")
    assert "dynamic_subtitle" in p


def test_regime_gate_stock_vs_market_context():
    gates = build_trading_gates(
        assessment_pct=20.0,
        regime_bull_pct=1.0,
        pattern_score=55.0,
        short_ml_prob=46.0,
        rsi=58.0,
        confidence_mid=50.0,
        include_confidence=False,
        ticker="GOOGL",
        regime_hmm_label="Transition",
        regime_transition_pct=99.0,
        market_regime_bull_pct=95.0,
    )
    regime = next(g for g in gates if g["id"] == "regime")
    assert "GOOGL" in regime["detail"]
    assert "95" in regime["detail"]
    assert "lagging" in regime["detail"].lower()


def test_momentum_rsi_58_above_neutral_not_extended():
    gates = build_trading_gates(
        assessment_pct=10.0,
        regime_bull_pct=70.0,
        pattern_score=40.0,
        short_ml_prob=30.0,
        rsi=58.0,
        confidence_mid=50.0,
        include_confidence=False,
    )
    mom = next(g for g in gates if g["id"] == "momentum")
    assert "above neutral" in mom["detail"].lower()
    assert "extended" not in mom["detail"].lower()


def test_ml_marginal_pass_at_46_pct():
    gates = build_trading_gates(
        assessment_pct=10.0,
        regime_bull_pct=70.0,
        pattern_score=55.0,
        short_ml_prob=46.0,
        rsi=45.0,
        confidence_mid=50.0,
        include_confidence=False,
    )
    ml = next(g for g in gates if g["id"] == "ml")
    assert ml["pass"] is True
    assert ml["visual_status"] == "marginal"
    assert "marginal" in ml["detail"].lower()


def _momentum_gate(**overrides):
    base = dict(
        assessment_pct=10.0,
        regime_bull_pct=70.0,
        pattern_score=60.0,
        short_ml_prob=40.0,
        rsi=40.0,
        confidence_mid=60.0,
        include_confidence=False,
        volume_ratio=0.6,
    )
    base.update(overrides)
    gates = build_trading_gates(**base)
    return next(g for g in gates if g["id"] == "momentum")


def test_momentum_obv_distribution_downgrades_to_marginal():
    """RSI/pattern clear the gate, but OBV shows net selling under a light-volume tape."""
    mom = _momentum_gate(obv_trend_pct=-15.0)
    assert mom["pass"] is True
    assert mom["visual_status"] == "marginal"
    assert mom["marginal_pass"] is True
    assert "lack of interest" in mom["detail"].lower()


def test_momentum_obv_accumulation_stays_cleared():
    """Same light-volume tape, but OBV is rising — lack of sellers, not lack of interest."""
    mom = _momentum_gate(obv_trend_pct=12.0)
    assert mom["pass"] is True
    assert mom["visual_status"] == "cleared"
    assert "lack of sellers" in mom["detail"].lower()


def test_momentum_obv_cannot_rescue_a_failing_gate():
    """OBV only tempers a pass — it never flips a failing RSI/pattern read to pass."""
    mom = _momentum_gate(rsi=65.0, pattern_score=20.0, obv_trend_pct=20.0)
    assert mom["pass"] is False
    assert mom["visual_status"] == "hot"


def test_momentum_no_obv_data_falls_back_to_prior_behavior():
    mom = _momentum_gate(obv_trend_pct=None)
    assert mom["pass"] is True
    assert mom["visual_status"] == "cleared"
    assert "obv" not in mom["detail"].lower()


def test_coherent_story_and_next_trigger():
    from signals.retail_action_payload import build_coherent_setup_story, build_next_trigger

    gates = build_trading_gates(
        assessment_pct=20.9,
        regime_bull_pct=1.0,
        pattern_score=55.0,
        short_ml_prob=46.0,
        rsi=58.0,
        confidence_mid=50.0,
        include_confidence=False,
        ticker="GOOGL",
        regime_transition_pct=99.0,
        market_regime_bull_pct=95.0,
    )
    story = build_coherent_setup_story(
        ticker="GOOGL",
        assessment_pct=20.9,
        stock_bull_pct=1.0,
        market_bull_pct=95.0,
        rsi=58.0,
        short_ml_prob=46.0,
        gates=gates,
        regime_transition_days=7,
    )
    assert "cheap" in story.lower() or "fair value" in story.lower()
    assert "Market Weather" in story or "entry trigger" in story.lower()
    trig = build_next_trigger(
        ticker="GOOGL",
        gates=gates,
        stock_bull_pct=1.0,
        market_bull_pct=95.0,
        regime_transition_days=7,
    )
    assert trig is not None
    assert "Market Weather" in trig["headline"]


def test_enrich_dashboard_signal_row():
    row = {
        "ticker": "NOW",
        "close": 103.42,
        "rsi": 61,
        "ml_short_prob": 0.33,
        "confluence_score": 52,
        "plan_action": "WATCH",
        "plan_confidence": 0.48,
        "_global_market_regime": "BEAR",
        "lt_band": {"low": 85, "high": 93},
        "st_band": {"low": 98, "high": 105},
    }
    enrich_dashboard_signal_row(row, regime_bull_pct=38)
    assert row["gate_cleared"] is False
    assert row["rsi_status"] == "hot"
    assert "retail_status" in row
    assert row["retail_status"]["action_title"]


def _anchor(**overrides):
    base = dict(
        close=95.0,
        ma50=100.0,
        high_52w=150.0,
        low_52w=92.0,
        momentum_extended=False,
        regime_ok=False,
    )
    base.update(overrides)
    return _price_anchor_clause(**base)


def test_price_anchor_below_ma50_and_near_low():
    clause = _anchor()
    assert "5.0% below its 50-day average ($100.00)" in clause
    assert "near its 52-week low ($92.00)" in clause
    assert "close back above that level" in clause


def test_price_anchor_below_ma50_not_near_low_omits_low_clause():
    clause = _anchor(low_52w=50.0)
    assert "below its 50-day average" in clause
    assert "52-week low" not in clause


def test_price_anchor_momentum_extended_near_high():
    clause = _anchor(close=148.0, ma50=140.0, momentum_extended=True, regime_ok=False)
    assert "near its 52-week high ($150.00)" in clause
    assert "mean-reversion risk" in clause
    # Momentum-extended framing takes priority over the below-MA50 framing when both
    # could technically apply (shouldn't happen in practice — high price, low MA50 —
    # but the branch order should still prefer the near-high read).


def test_price_anchor_near_low_only_when_regime_ok():
    """A confirmed bull regime that happens to be near its 52w low still gets flagged —
    the anchor is about price proximity, not gate state, when momentum isn't extended."""
    clause = _anchor(regime_ok=True)
    assert "within 5% of its 52-week low ($92.00)" in clause


def test_price_anchor_no_data_returns_empty():
    assert _price_anchor_clause(
        close=None, ma50=None, high_52w=None, low_52w=None,
        momentum_extended=False, regime_ok=False,
    ) == ""


def test_price_anchor_bull_far_from_any_extreme_is_empty():
    clause = _anchor(close=120.0, ma50=115.0, regime_ok=True)
    assert clause == ""


def test_build_trading_gates_regime_detail_includes_price_anchor():
    gates = build_trading_gates(
        assessment_pct=10.0,
        regime_bull_pct=25.0,
        pattern_score=60.0,
        short_ml_prob=40.0,
        rsi=45.0,
        confidence_mid=60.0,
        include_confidence=False,
        ticker="AMZN",
        close=95.0,
        ma50=100.0,
        high_52w=150.0,
        low_52w=92.0,
    )
    regime = next(g for g in gates if g["id"] == "regime")
    assert "below its 50-day average" in regime["detail"]
    assert "$100.00" in regime["detail"]


def test_build_trading_gates_regime_detail_degrades_without_price_data():
    """No new params supplied -> exactly today's text, no trailing clause."""
    gates = build_trading_gates(
        assessment_pct=10.0,
        regime_bull_pct=25.0,
        pattern_score=60.0,
        short_ml_prob=40.0,
        rsi=45.0,
        confidence_mid=60.0,
        include_confidence=False,
        ticker="AMZN",
    )
    regime = next(g for g in gates if g["id"] == "regime")
    assert regime["detail"] == "Stormy Tape — AMZN HMM non-bull (25% bull)"
