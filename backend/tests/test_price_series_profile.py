"""Tests for price series profiling and sector metadata."""
from __future__ import annotations

import pandas as pd

from signals.price_series_profile import analyze_price_series, trim_to_listing_date
from signals.ticker_metadata import resolve_equity_sector, sector_from_industry


def test_sector_from_industry_semiconductor():
    assert sector_from_industry("Semiconductors") == "Technology"


def test_resolve_sndk_sector():
    out = resolve_equity_sector("SNDK")
    assert out["sector"] == "Technology"
    assert out["sector_etf"] == "XLK"


def test_resolve_unknown_industry_fallback():
    out = resolve_equity_sector("XYZ", sector=None, industry="Regional Banks")
    assert out["sector"] == "Financials"


def test_analyze_extreme_range_adjusts_52w_low():
    # Simulate spin-off: $36 → $1500
    dates = pd.date_range("2025-02-24", periods=280, freq="B")
    prices = [36 + i * 5.5 for i in range(len(dates))]
    close = pd.Series(prices, index=dates)
    profile = analyze_price_series(close, float(close.iloc[-1]), ticker="SNDK")
    assert profile["ok"] is True
    assert profile["extreme_52w_range"] is True
    assert profile["effective_52w_low"] > profile["raw_52w_low"] * 2
    assert profile["effective_ma200"] > profile["raw_ma200"]


def test_trim_to_listing_date():
    dates = pd.date_range("2024-01-01", periods=400, freq="B")
    close = pd.Series(range(400), index=dates, dtype=float)
    trimmed = trim_to_listing_date("SNDK", close)
    assert trimmed.index[0] >= pd.Timestamp("2025-02-24")
