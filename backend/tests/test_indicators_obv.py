"""Tests for OBV / obv_trend_pct — accumulation vs distribution disambiguation."""

from __future__ import annotations

import pandas as pd

from signals.indicators import compute_obv, obv_trend_pct


def test_compute_obv_direction_signed():
    close = pd.Series([100.0, 101.0, 100.5, 102.0])
    volume = pd.Series([1000.0, 1000.0, 1000.0, 1000.0])
    obv = compute_obv(close, volume)
    # day0: no prior diff -> 0; day1: up -> +1000; day2: down -> -1000; day3: up -> +1000
    assert obv.tolist() == [0.0, 1000.0, 0.0, 1000.0]


def test_obv_trend_pct_accumulation_positive():
    close = pd.Series([100 + i for i in range(15)])
    volume = pd.Series([1000.0] * 15)
    assert obv_trend_pct(close, volume, window=10) > 0


def test_obv_trend_pct_distribution_negative():
    close = pd.Series([100 - i for i in range(15)])
    volume = pd.Series([1000.0] * 15)
    assert obv_trend_pct(close, volume, window=10) < 0


def test_obv_trend_pct_flat_is_zero():
    close = pd.Series([100.0] * 15)
    volume = pd.Series([1000.0] * 15)
    assert obv_trend_pct(close, volume, window=10) == 0.0


def test_obv_trend_pct_insufficient_history_returns_none():
    close = pd.Series([100.0, 101.0, 102.0])
    volume = pd.Series([1000.0, 1000.0, 1000.0])
    assert obv_trend_pct(close, volume, window=10) is None
