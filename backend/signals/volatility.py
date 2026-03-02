"""
Volatility utilities (daily timeframe).

Primary use: ATR(14) computed from True Range on daily OHLC data.
This is used for stop levels, loss scenarios, and position sizing.
"""

from __future__ import annotations

import pandas as pd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """
    True Range (TR) per Wilder:
      TR = max(
        High - Low,
        abs(High - prevClose),
        abs(Low  - prevClose)
      )
    """
    high = pd.Series(high).astype(float)
    low = pd.Series(low).astype(float)
    close = pd.Series(close).astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr_series_wilder(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """
    ATR series using Wilder's smoothing (RMA with alpha=1/window).

    Note: pandas ewm(alpha=1/window, adjust=False) matches Wilder's RMA form.
    """
    tr = true_range(high, low, close)
    atr = tr.ewm(alpha=1.0 / float(window), adjust=False, min_periods=window).mean()
    return atr


def atr14_from_ohlcv_df(df: pd.DataFrame | None) -> float | None:
    """Convenience: compute latest ATR(14) from a df with columns high/low/close."""
    if df is None or df.empty:
        return None
    for col in ("high", "low", "close"):
        if col not in df.columns:
            return None
    atr = atr_series_wilder(df["high"], df["low"], df["close"], window=14).dropna()
    if atr.empty:
        return None
    val = float(atr.iloc[-1])
    return round(val, 2) if val > 0 else None

