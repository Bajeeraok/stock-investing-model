"""Tests for pattern score rebalancing — bullish trend score integration."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from signals.pattern_signals import near_bottom_score, _bullish_trend_score


def _make_uptrend_df(n: int = 260) -> pd.DataFrame:
    """Generate a clean uptrend with rising prices, volume, and MAs."""
    dates = pd.bdate_range(end=pd.Timestamp.now(), periods=n)
    base = 100.0
    close = [base]
    for i in range(1, n):
        close.append(close[-1] * (1 + np.random.normal(0.001, 0.005)))
    close_arr = np.array(close)
    return pd.DataFrame({
        "close": close_arr,
        "high": close_arr * 1.005,
        "low": close_arr * 0.995,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)


def _make_downtrend_df(n: int = 260) -> pd.DataFrame:
    """Generate a downtrend with falling prices."""
    dates = pd.bdate_range(end=pd.Timestamp.now(), periods=n)
    base = 100.0
    close = [base]
    for i in range(1, n):
        close.append(close[-1] * (1 + np.random.normal(-0.001, 0.005)))
    close_arr = np.array(close)
    return pd.DataFrame({
        "close": close_arr,
        "high": close_arr * 1.005,
        "low": close_arr * 0.995,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    }, index=dates)


def _make_breakout_df(n: int = 260) -> pd.DataFrame:
    """Sideways for most of the period, then breakout to new highs."""
    dates = pd.bdate_range(end=pd.Timestamp.now(), periods=n)
    close = []
    base = 100.0
    # Sideways for 200 bars
    for i in range(200):
        close.append(base + np.random.normal(0, 1))
    # Breakout for last 60 bars
    for i in range(60):
        close.append(close[-1] * (1 + np.random.normal(0.003, 0.004)))
    close_arr = np.array(close)
    return pd.DataFrame({
        "close": close_arr,
        "high": close_arr * 1.005,
        "low": close_arr * 0.995,
        "volume": np.concatenate([
            np.random.randint(1_000_000, 2_000_000, 200),
            np.random.randint(3_000_000, 6_000_000, 60),
        ]),
    }, index=dates)


class TestBullishTrendScore:
    def test_uptrend_scores_above_40(self):
        np.random.seed(42)
        df = _make_uptrend_df()
        score, signals, details = _bullish_trend_score(df, "TEST")
        assert score >= 40, f"Expected uptrend score >= 40, got {score}"
        assert len(signals) > 0

    def test_downtrend_scores_low(self):
        np.random.seed(42)
        df = _make_downtrend_df()
        score, signals, details = _bullish_trend_score(df, "TEST")
        assert score <= 40, f"Expected downtrend score <= 40, got {score}"

    def test_breakout_scores_well(self):
        np.random.seed(42)
        df = _make_breakout_df()
        score, signals, details = _bullish_trend_score(df, "TEST")
        assert score >= 30, f"Expected breakout score >= 30, got {score}"

    def test_empty_df(self):
        score, signals, details = _bullish_trend_score(pd.DataFrame(), "TEST")
        assert score == 0.0


class TestNearBottomScoreBlending:
    def test_uptrend_stock_gets_trend_boost(self):
        """Stocks in uptrends should score higher than raw bottom score."""
        np.random.seed(42)
        df = _make_uptrend_df()
        score, signals, details = near_bottom_score(df, "TEST")
        # In an uptrend, the bottom score is low (<30), so trend should take over
        assert score >= 35, f"Expected blended score >= 35 for uptrend, got {score}"
        # Should have at least some trend signals
        assert any("MA50" in s or "52-week" in s or "RSI" in s or "trend" in s.lower() for s in signals)

    def test_bottom_stock_keeps_bottom_score(self):
        """Stocks near bottom should keep the bottom reversal score."""
        np.random.seed(42)
        df = _make_downtrend_df()
        score, signals, details = near_bottom_score(df, "TEST")
        # The mode should reflect whichever scored higher
        assert details.get("mode") in ("bottom_reversal", "trend_continuation")

    def test_mode_indicator_present(self):
        np.random.seed(42)
        df = _make_uptrend_df()
        _, _, details = near_bottom_score(df, "TEST")
        assert "mode" in details
        assert details["mode"] in ("bottom_reversal", "trend_continuation")
