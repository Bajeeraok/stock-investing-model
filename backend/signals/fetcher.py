"""
Fetch daily OHLCV. Handles missing data and short history.
"""
from __future__ import annotations

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None


def fetch_ohlcv(ticker: str, period: str = "5y") -> pd.Series | None:
    """
    Download adjusted close for ticker. Returns None if insufficient data or error.
    """
    if yf is None:
        raise ImportError("Install yfinance: pip install yfinance")

    try:
        data = yf.download(ticker, period=period, progress=False, threads=False, auto_adjust=True)
    except Exception:
        return None

    if data is None or data.empty or len(data) < 50:
        return None

    # yfinance: single ticker -> columns like Open, Close; multi -> MultiIndex
    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"].iloc[:, 0] if data["Close"].ndim > 1 else data["Close"]
    else:
        for col in ("Adj Close", "Close"):
            if col in data.columns:
                close = data[col]
                break
        else:
            close = data.iloc[:, 0]

    close = pd.Series(close, name="close").dropna()
    if len(close) < 50:
        return None
    return close


def fetch_ohlcv_safe(ticker: str, period: str = "5y") -> pd.Series | None:
    """Same as fetch_ohlcv but swallows errors and returns None."""
    try:
        return fetch_ohlcv(ticker, period)
    except Exception:
        return None


def fetch_ohlcv_with_volume(ticker: str, period: str = "5y") -> tuple[pd.Series | None, pd.Series | None]:
    """Fetch close and volume. Returns (close, volume) or (close, None) if volume unavailable."""
    if yf is None:
        return None, None
    try:
        data = yf.download(ticker, period=period, progress=False, threads=False, auto_adjust=True)
    except Exception:
        return None, None
    if data is None or data.empty or len(data) < 20:
        return None, None
    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"].iloc[:, 0] if data["Close"].ndim > 1 else data["Close"]
        vol = data["Volume"].iloc[:, 0] if "Volume" in data.columns and data["Volume"].ndim > 1 else (data["Volume"] if "Volume" in data.columns else None)
    else:
        for col in ("Adj Close", "Close"):
            if col in data.columns:
                close = data[col]
                break
        else:
            close = data.iloc[:, 0]
        vol = data["Volume"] if "Volume" in data.columns else None
    close = pd.Series(close, name="close").dropna()
    if len(close) < 20:
        return None, None
    volume = pd.Series(vol, name="volume").dropna() if vol is not None and not vol.empty else None
    return close, volume


def fetch_ohlcv_with_config(ticker: str, period: str, config: dict | None) -> pd.Series | None:
    """Use FMP if api_key in config, else yfinance."""
    try:
        from .providers import fetch_ohlcv as fetch_provider
        return fetch_provider(ticker, period, config)
    except Exception:
        return fetch_ohlcv_safe(ticker, period)
