"""
Data providers: yfinance (free), FMP (optional, API key required).
FMP: https://financialmodelingprep.com/developer/docs - add api_key to config.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import urllib.request
    import urllib.parse
    import json as _json
except ImportError:
    urllib = None


def fetch_ohlcv(ticker: str, period: str = "5y", config: dict | None = None) -> pd.Series | None:
    """
    Fetch OHLCV close. Uses FMP if api_key in config, else yfinance.
    """
    config = config or {}
    api_key = config.get("data", {}).get("fmp_api_key") or config.get("fmp_api_key")

    if api_key:
        close = _fetch_ohlcv_fmp(ticker, period, api_key)
        if close is not None:
            return close
    return _fetch_ohlcv_yfinance(ticker, period)


def _fetch_ohlcv_yfinance(ticker: str, period: str) -> pd.Series | None:
    if yf is None:
        return None
    try:
        data = yf.download(ticker, period=period, progress=False, threads=False, auto_adjust=True)
    except Exception:
        return None
    if data is None or data.empty or len(data) < 50:
        return None
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
    return close if len(close) >= 50 else None


def _fetch_ohlcv_fmp(ticker: str, period: str, api_key: str) -> pd.Series | None:
    if urllib is None:
        return None
    years = {"1mo": 0.1, "3mo": 0.25, "6mo": 0.5, "1y": 1, "2y": 2, "5y": 5, "10y": 10}.get(period, 5)
    to_dt = datetime.now().date()
    from_dt = (to_dt - timedelta(days=int(years * 365))).isoformat()
    url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}?from={from_dt}&to={to_dt}&apikey={api_key}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as resp:
            data = _json.loads(resp.read().decode())
    except Exception:
        return None
    hist = data.get("historical")
    if not hist or len(hist) < 50:
        return None
    df = pd.DataFrame(hist)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    close = df["adjClose"] if "adjClose" in df.columns else df["close"]
    return close.dropna()


# ETFs have no earnings; skip to avoid yfinance 404 noise
_ETFS = frozenset({"SPY", "QQQ", "GLD", "SLV", "DIA", "IWM", "XLF", "XLK", "XLE", "XLV", "XLP", "XLY", "XLI", "XLB", "XLU"})


def get_next_earnings(ticker: str, config: dict | None = None) -> dict | None:
    """
    Get next earnings date. Returns {date, days_until} or None.
    Uses yfinance (free) or FMP if api_key configured.
    """
    if ticker.upper() in _ETFS:
        return None
    config = config or {}
    api_key = config.get("data", {}).get("fmp_api_key") or config.get("fmp_api_key")

    if api_key:
        info = _get_earnings_fmp(ticker, api_key)
        if info:
            return info
    return _get_earnings_yfinance(ticker)


def _get_earnings_yfinance(ticker: str) -> dict | None:
    if yf is None:
        return None
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None or (isinstance(cal, dict) and not cal):
            # Try earnings_dates
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                future = ed[ed.index >= pd.Timestamp.now().tz_localize(None)]
                if not future.empty:
                    next_d = future.index[0]
                    if isinstance(next_d, pd.Timestamp):
                        days = (next_d - pd.Timestamp.now()).days
                        return {"date": next_d.strftime("%Y-%m-%d"), "days_until": days}
            return None
        if isinstance(cal, dict) and "Earnings Date" in cal:
            raw = cal["Earnings Date"]
            if isinstance(raw, list) and raw:
                d = raw[0]
                if hasattr(d, "strftime"):
                    days = (d - datetime.now().date()).days if hasattr(d, "day") else None
                    return {"date": d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d), "days_until": days}
    except Exception:
        pass
    return None


def _get_earnings_fmp(ticker: str, api_key: str) -> dict | None:
    if urllib is None:
        return None
    url = f"https://financialmodelingprep.com/api/v3/earning_calendar?symbol={ticker}&apikey={api_key}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as resp:
            data = _json.loads(resp.read().decode())
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None
    today = datetime.now().date()
    for item in data:
        d_str = item.get("date")
        if not d_str:
            continue
        try:
            d = datetime.strptime(d_str[:10], "%Y-%m-%d").date()
            if d >= today:
                days = (d - today).days
                return {"date": d_str[:10], "days_until": days}
        except Exception:
            continue
    return None
