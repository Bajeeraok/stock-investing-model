"""Synthetic correlation / sizing tests (no market data)."""
import numpy as np
import pandas as pd

from signals.portfolio_risk_model import correlation_adjusted_sizing


def test_correlation_adjusted_sizing_reduces_when_correlated(monkeypatch):
    dates = pd.date_range("2020-01-01", periods=100, freq="B")
    r = np.random.default_rng(0)
    base = r.normal(0, 0.01, size=len(dates))
    # A and B almost identical → high correlation
    s_a = pd.Series((1 + base).cumprod(), index=dates)
    s_b = pd.Series((1 + base + r.normal(0, 0.0001, size=len(dates))).cumprod(), index=dates)

    def fake_fetch(t, period):
        if t == "AAA":
            return s_a
        if t == "BBB":
            return s_b
        return None

    out = correlation_adjusted_sizing(
        ["AAA", "BBB"],
        {"AAA": 0.25, "BBB": 0.25},
        max_portfolio=0.65,
        fetch_close=fake_fetch,
    )
    assert out["AAA"] < 0.25
    assert out["BBB"] < 0.25
