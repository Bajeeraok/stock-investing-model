"""Tests for signals.beta_utils and portfolio beta bundle."""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals.beta_utils import compute_beta, compute_beta_from_returns
from signals.portfolio_risk_model import compute_portfolio_beta_metrics


def _make_series(beta_target: float, n: int = 300, seed: int = 0) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    spy_rets = rng.normal(0.0004, 0.01, size=n)
    asset_rets = beta_target * spy_rets + rng.normal(0, 0.002, size=n)
    spy = pd.Series((1 + spy_rets).cumprod(), index=dates)
    asset = pd.Series((1 + asset_rets).cumprod(), index=dates)
    return asset, spy


def test_compute_beta_synthetic():
    asset, spy = _make_series(1.5, seed=1)
    beta = compute_beta(asset, spy)
    assert beta is not None
    assert 1.2 < beta < 1.8


def test_compute_beta_from_returns():
    asset, spy = _make_series(0.6, seed=2)
    a_rets = asset.pct_change().dropna()
    s_rets = spy.pct_change().dropna()
    beta = compute_beta_from_returns(a_rets, s_rets)
    assert beta is not None
    assert 0.4 < beta < 0.9


def test_portfolio_beta_metrics_weighted(monkeypatch):
    dates = pd.date_range("2022-01-01", periods=300, freq="B")
    rng = np.random.default_rng(3)
    spy_rets = rng.normal(0.0004, 0.01, size=len(dates))
    spy = pd.Series((1 + spy_rets).cumprod(), index=dates)

    def high_beta_rets():
        return 1.8 * spy_rets + rng.normal(0, 0.001, size=len(dates))

    def low_beta_rets():
        return 0.5 * spy_rets + rng.normal(0, 0.001, size=len(dates))

    aaa = pd.Series((1 + high_beta_rets()).cumprod(), index=dates)
    bbb = pd.Series((1 + low_beta_rets()).cumprod(), index=dates)

    def fake_fetch(t, period):
        if t == "SPY":
            return spy
        if t == "AAA":
            return aaa
        if t == "BBB":
            return bbb
        return None

    def fake_sector(t):
        if t == "AAA":
            return {"sector": "Technology"}
        return {"sector": "Healthcare"}

    monkeypatch.setattr(
        "signals.providers.get_sector_and_industry",
        lambda t: fake_sector(t),
    )

    out = compute_portfolio_beta_metrics(
        [
            {"ticker": "AAA", "value": 6000, "pct": 60},
            {"ticker": "BBB", "value": 4000, "pct": 40},
        ],
        fetch_close=fake_fetch,
    )
    assert out.get("portfolio_beta") is not None
    assert 1.0 < out["portfolio_beta"] < 2.0
    assert out["coverage_pct"] == 100.0
    assert len(out["holdings"]) == 2
    assert len(out["sectors"]) >= 2
    assert "headline" in out
    assert "× the market" in out["headline"]
