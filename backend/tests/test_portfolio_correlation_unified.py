"""Tests for the unified correlation implementation (portfolio_risk_model.py) that
portfolio/doctor.py now calls instead of maintaining its own separate pairwise-correlation
calc — see docs/signals/RETAIL_DATA_SURFACING.md."""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.portfolio_risk_model import (
    _period_for_lookback_days,
    compute_correlation_matrix,
    correlation_to_holdings,
)


def test_period_for_lookback_days_mapping():
    assert _period_for_lookback_days(20) == "1mo"
    assert _period_for_lookback_days(60) == "3mo"
    assert _period_for_lookback_days(150) == "6mo"
    assert _period_for_lookback_days(252) == "1y"
    assert _period_for_lookback_days(756) == "3y"
    assert _period_for_lookback_days(1260) == "5y"


def test_default_lookback_still_resolves_to_5y():
    """Backward-compat: the old hardcoded '5y' behavior is preserved at the default."""
    assert _period_for_lookback_days(1260) == "5y"


def _fake_fetch_factory(seed_map: dict[str, int]):
    def fetch_close(ticker: str, period: str) -> pd.Series:
        rng = np.random.default_rng(seed_map[ticker])
        idx = pd.date_range("2024-01-01", periods=120, freq="B")
        return pd.Series(100 + np.cumsum(rng.normal(0, 1, size=120)), index=idx)

    return fetch_close


def test_correlation_matrix_respects_custom_lookback_and_fetch():
    fetch = _fake_fetch_factory({"AAA": 1, "BBB": 2, "CCC": 3})
    corr, err = compute_correlation_matrix(["AAA", "BBB", "CCC"], lookback_days=60, fetch_close=fetch)
    assert err is None
    assert corr is not None
    assert set(corr.columns) == {"AAA", "BBB", "CCC"}
    # Self-correlation is always 1.0
    assert corr.loc["AAA", "AAA"] == 1.0


def test_correlation_matrix_needs_at_least_two_tickers_with_history():
    def fetch_close(ticker, period):
        return None

    corr, err = compute_correlation_matrix(["AAA"], fetch_close=fetch_close)
    assert corr is None
    assert err is not None


def test_correlation_to_holdings_shapes_candidate_vs_each_holding():
    fetch = _fake_fetch_factory({"NEW": 1, "AAA": 2, "BBB": 3})
    result = correlation_to_holdings("new", ["AAA", "bbb"], fetch_close=fetch)
    assert result["available"] is True
    assert result["ticker"] == "NEW"
    assert {p["ticker"] for p in result["correlations"]} == {"AAA", "BBB"}
    assert all(-1.0 <= p["correlation"] <= 1.0 for p in result["correlations"])
    assert result["avg_correlation"] is not None


def test_correlation_to_holdings_empty_inputs_unavailable():
    assert correlation_to_holdings("", ["AAA"])["available"] is False
    assert correlation_to_holdings("NEW", [])["available"] is False


def test_correlation_to_holdings_propagates_underlying_error():
    def fetch_close(ticker, period):
        return None

    result = correlation_to_holdings("NEW", ["AAA"], fetch_close=fetch_close)
    assert result["available"] is False
    assert result.get("reason")
