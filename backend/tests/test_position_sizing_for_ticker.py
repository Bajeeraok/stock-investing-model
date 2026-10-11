"""
Regression coverage for signals/tier1_risk_engine.py's ticker-detail-facing additions:
regime_label_from_bull_pct() and size_position_for_ticker().

Context: Position Build's sizing_block (signals/horizon_playbooks.py) previously computed
$/share recommendations against a hardcoded example_portfolio = $50,000 placeholder — never
the user's real portfolio value or their real existing position in the ticker. The full Kelly-
based PositionSizingEngine already existed and already handles incremental sizing (subtracts
what's already held) and concentration caps, but was only wired into the Tier 1 batch pipeline
for currently-held tickers, not callable for an arbitrary ticker being looked up in the detail
view. size_position_for_ticker() is the missing bridge.
"""
from __future__ import annotations

from signals.tier1_risk_engine import regime_label_from_bull_pct, size_position_for_ticker


def test_regime_label_thresholds():
    assert regime_label_from_bull_pct(85) == "STRONG_BULL"
    assert regime_label_from_bull_pct(60) == "BULL"
    assert regime_label_from_bull_pct(50) == "NEUTRAL"
    assert regime_label_from_bull_pct(35) == "BEAR"
    assert regime_label_from_bull_pct(10) == "STRONG_BEAR"


def test_regime_label_none_defaults_to_neutral():
    assert regime_label_from_bull_pct(None) == "NEUTRAL"


def test_size_position_returns_none_without_a_real_portfolio_value():
    """Showing a $/share recommendation against a made-up portfolio size is worse than
    showing none — this is the direct fix for the $50,000 example_portfolio placeholder."""
    assert size_position_for_ticker(ticker="AAPL", price=250.0, portfolio_value=0) is None
    assert size_position_for_ticker(ticker="AAPL", price=250.0, portfolio_value=None) is None
    assert size_position_for_ticker(ticker="AAPL", price=0, portfolio_value=50_000) is None


def test_size_position_tranches_sum_to_recommended_shares():
    out = size_position_for_ticker(
        ticker="AAPL", price=250.0, portfolio_value=50_000.0,
        signal_score=78, confidence=0.70, atr_14=5.0, vix=18.0, regime_bull_pct=65,
    )
    assert out is not None
    assert sum(t["shares"] for t in out["tranches"]) == out["recommended_shares"]
    assert len(out["tranches"]) == 3


def test_size_position_is_incremental_not_double_counted():
    """Already holding most of the target allocation -> near-zero further add, not a second
    full-size recommendation stacked on top of the existing position."""
    fresh = size_position_for_ticker(
        ticker="AAPL", price=250.0, portfolio_value=50_000.0,
        current_position_value=0.0, signal_score=78, confidence=0.70,
        atr_14=5.0, vix=18.0, regime_bull_pct=65,
    )
    already_large = size_position_for_ticker(
        ticker="AAPL", price=250.0, portfolio_value=50_000.0,
        current_position_value=9_500.0, signal_score=78, confidence=0.70,
        atr_14=5.0, vix=18.0, regime_bull_pct=65,
    )
    assert fresh is not None and already_large is not None
    assert already_large["recommended_dollars"] < fresh["recommended_dollars"]
    assert already_large["current_pct"] == 0.19


def test_size_position_respects_concentration_cap_even_with_huge_portfolio():
    out = size_position_for_ticker(
        ticker="AAPL", price=250.0, portfolio_value=1_000_000.0,
        signal_score=95, confidence=0.95, atr_14=3.0, vix=12.0, regime_bull_pct=90,
    )
    assert out is not None
    # Moderate risk tolerance caps a single name at 20% of portfolio.
    assert out["recommended_dollars"] + out["current_position_value"] <= out["max_position_dollars"] + 1e-6


def test_size_position_falls_back_atr_and_vix_when_missing():
    """Missing ATR/VIX must not raise or silently zero the result — falls back to a
    price-based ATR proxy and a neutral default VIX, same convention used elsewhere in
    ticker_detail.py (current_price * 0.02)."""
    out = size_position_for_ticker(ticker="AAPL", price=250.0, portfolio_value=50_000.0)
    assert out is not None
    assert out["recommended_shares"] >= 0


def test_size_position_missing_regime_defaults_neutral_not_crash():
    out = size_position_for_ticker(ticker="AAPL", price=250.0, portfolio_value=50_000.0, regime_bull_pct=None)
    assert out is not None
    assert out["regime_used"] == "NEUTRAL"
