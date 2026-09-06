"""Tests for session_vwap.compute_session_vwap — real single-session VWAP from free
intraday bars, distinct from thrive_phase2's rolling 5-day VWAP and from
ticker_detail.py's `vwap = current_price` band-math stand-in (see module docstring).
"""

from __future__ import annotations

import pandas as pd
import pytest

from signals.session_vwap import compute_session_vwap


class _FakeTicker:
    def __init__(self, df: pd.DataFrame | None):
        self._df = df

    def history(self, period: str = "1d", interval: str = "5m") -> pd.DataFrame:
        if self._df is None:
            raise RuntimeError("no data")
        return self._df


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """rows of (high, low, close, volume)."""
    idx = pd.date_range("2027-01-04 09:30", periods=len(rows), freq="5min")
    return pd.DataFrame(
        {
            "High": [r[0] for r in rows],
            "Low": [r[1] for r in rows],
            "Close": [r[2] for r in rows],
            "Volume": [r[3] for r in rows],
        },
        index=idx,
    )


def test_computes_expected_vwap(monkeypatch):
    # Three bars, equal volume: typical prices 100, 102, 104 -> VWAP = 102.
    df = _bars([
        (101, 99, 100, 1000),
        (103, 101, 102, 1000),
        (105, 103, 104, 1000),
    ])
    monkeypatch.setattr("yfinance.Ticker", lambda ticker: _FakeTicker(df))

    out = compute_session_vwap("TEST")
    assert out is not None
    assert out["vwap"] == pytest.approx(102.0, abs=0.01)
    assert out["bars_used"] == 3
    # close (104) is above vwap (102) -> positive pct
    assert out["close_vs_vwap_pct"] > 0


def test_returns_none_on_empty_dataframe(monkeypatch):
    monkeypatch.setattr("yfinance.Ticker", lambda ticker: _FakeTicker(pd.DataFrame()))
    assert compute_session_vwap("TEST") is None


def test_returns_none_on_too_few_bars(monkeypatch):
    df = _bars([(101, 99, 100, 1000)])
    monkeypatch.setattr("yfinance.Ticker", lambda ticker: _FakeTicker(df))
    assert compute_session_vwap("TEST") is None


def test_returns_none_on_zero_volume(monkeypatch):
    df = _bars([(101, 99, 100, 0), (103, 101, 102, 0), (104, 102, 103, 0)])
    monkeypatch.setattr("yfinance.Ticker", lambda ticker: _FakeTicker(df))
    assert compute_session_vwap("TEST") is None


def test_returns_none_on_fetch_failure(monkeypatch):
    monkeypatch.setattr("yfinance.Ticker", lambda ticker: _FakeTicker(None))
    assert compute_session_vwap("TEST") is None


def test_returns_none_when_yfinance_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("no yfinance")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert compute_session_vwap("TEST") is None
