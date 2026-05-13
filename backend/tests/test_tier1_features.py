"""Tests for Tier 1 features: attribution, liquidity, factor exposure."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# ─── Attribution ───
class TestAttribution:
    def _mock_close(self, start=100, end=110, days=252):
        dates = pd.bdate_range(end=datetime.now(), periods=days)
        prices = np.linspace(start, end, days)
        return pd.Series(prices, index=dates)

    def test_basic_attribution(self):
        from portfolio.attribution import compute_attribution
        holdings = [
            {"ticker": "NVDA", "value": 5000, "pct": 50},
            {"ticker": "AAPL", "value": 3000, "pct": 30},
            {"ticker": "GLD", "value": 2000, "pct": 20},
        ]
        closes = {
            "NVDA": self._mock_close(100, 150, 252),  # +50%
            "AAPL": self._mock_close(100, 110, 252),   # +10%
            "GLD": self._mock_close(100, 95, 252),     # -5%
        }
        result = compute_attribution(
            holdings, 10000,
            fetch_close=lambda t, p: closes.get(t),
        )
        assert "1m" in result["periods"]
        assert "YTD" in result["periods"]
        items_1m = result["periods"]["1m"]
        assert len(items_1m) == 3
        assert all("contribution_pct" in i for i in items_1m)

    def test_top_contributor_detractor(self):
        from portfolio.attribution import compute_attribution
        holdings = [
            {"ticker": "WIN", "value": 5000, "pct": 50},
            {"ticker": "LOSE", "value": 5000, "pct": 50},
        ]
        closes = {
            "WIN": self._mock_close(100, 130, 252),
            "LOSE": self._mock_close(100, 80, 252),
        }
        result = compute_attribution(holdings, 10000, fetch_close=lambda t, p: closes.get(t))
        assert result["top_contributor"]["ticker"] == "WIN"
        assert result["top_contributor"]["contribution_pct"] > 0
        assert result["top_detractor"]["ticker"] == "LOSE"
        assert result["top_detractor"]["contribution_pct"] < 0

    def test_empty_portfolio(self):
        from portfolio.attribution import compute_attribution
        result = compute_attribution([], 0)
        assert result["periods"] == {}

    def test_sorted_by_contribution(self):
        from portfolio.attribution import compute_attribution
        holdings = [
            {"ticker": "A", "value": 3000, "pct": 30},
            {"ticker": "B", "value": 5000, "pct": 50},
            {"ticker": "C", "value": 2000, "pct": 20},
        ]
        closes = {
            "A": self._mock_close(100, 90, 252),
            "B": self._mock_close(100, 140, 252),
            "C": self._mock_close(100, 105, 252),
        }
        result = compute_attribution(holdings, 10000, fetch_close=lambda t, p: closes.get(t))
        items = result["periods"]["1m"]
        contribs = [i["contribution_pct"] for i in items if i["contribution_pct"] is not None]
        assert contribs == sorted(contribs, reverse=True)


# ─── Liquidity ───
class TestLiquidity:
    def test_liquid_position(self):
        from portfolio.liquidity import compute_liquidity_scores
        holdings = [{"ticker": "AAPL", "quantity": 100, "price": 200, "pct": 20}]
        vol = pd.Series([50_000_000] * 63, index=pd.bdate_range(end=datetime.now(), periods=63))
        close = pd.Series([200] * 63, index=vol.index)
        result = compute_liquidity_scores(
            holdings,
            fetch_close_volume=lambda t, p: (close, vol),
        )
        items = result["items"]
        assert len(items) == 1
        assert items[0]["days_to_exit"] < 1
        assert items[0]["liquidity_score"] <= 2

    def test_illiquid_position(self):
        from portfolio.liquidity import compute_liquidity_scores
        holdings = [{"ticker": "MICRO", "quantity": 500_000, "price": 10, "pct": 5}]
        vol = pd.Series([10_000] * 63, index=pd.bdate_range(end=datetime.now(), periods=63))
        close = pd.Series([10] * 63, index=vol.index)
        result = compute_liquidity_scores(
            holdings,
            fetch_close_volume=lambda t, p: (close, vol),
        )
        items = result["items"]
        assert items[0]["days_to_exit"] > 5
        assert items[0]["liquidity_score"] >= 4
        assert result["illiquid_count"] >= 1
        assert result["note"] is not None

    def test_no_volume_data(self):
        from portfolio.liquidity import compute_liquidity_scores
        holdings = [{"ticker": "XXX", "quantity": 100, "price": 50, "pct": 10}]
        result = compute_liquidity_scores(
            holdings,
            fetch_close_volume=lambda t, p: (None, None),
        )
        assert result["items"][0]["liquidity_score"] is None


# ─── Factor Exposure ───
class TestFactorExposure:
    def test_etf_fixed_profile(self):
        from portfolio.factor_exposure import compute_factor_exposure
        holdings = [
            {"ticker": "QQQ", "pct": 60, "value": 6000},
            {"ticker": "SPY", "pct": 40, "value": 4000},
        ]
        result = compute_factor_exposure(holdings, 10000)
        pf = result["portfolio_factors"]
        assert "momentum" in pf
        assert "value" in pf
        assert "quality" in pf
        # QQQ is 70% momentum weighted 60%, SPY is 50% weighted 40%
        assert pf["momentum"] > 55

    def test_dominant_factor(self):
        from portfolio.factor_exposure import compute_factor_exposure
        holdings = [{"ticker": "QQQ", "pct": 100, "value": 10000}]
        result = compute_factor_exposure(holdings, 10000)
        assert result["dominant_factor"] == "growth"

    def test_empty_portfolio(self):
        from portfolio.factor_exposure import compute_factor_exposure
        result = compute_factor_exposure([], 0)
        assert result["portfolio_factors"] == {}

    def test_score_functions(self):
        from portfolio.factor_exposure import _score_momentum, _score_value, _score_size, _score_quality
        assert _score_momentum(50) > 75
        assert _score_momentum(-30) < 35
        assert _score_value(10) > 75
        assert _score_value(60) < 35
        assert _score_size(1e9) > 30   # $1B = small/mid
        assert _score_size(1e12) < 15  # $1T = mega-cap
        assert _score_quality(25, 30) > 60
        assert _score_quality(5, 5) < 40
