"""
Fetch daily OHLCV. Handles missing data and short history.

Extended period support:
  yfinance only accepts period strings up to "10y". For longer histories
  (e.g. "17y" to capture 2007-2024 including the financial crisis),
  _resolve_download_kwargs() converts "Ny" where N > 10 into a start= date.
  This means "17y", "16y", "15y" all work transparently.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)

# yfinance only accepts these period strings natively
_YF_NATIVE_PERIODS = {"1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"}


def _resolve_download_kwargs(period: str) -> dict:
    """
    Convert a period string to yfinance download kwargs.

    Native periods (≤ 10y, 'max', 'ytd') are passed as period=.
    Extended periods like '17y', '16y', '15y' are converted to start= date
    because yfinance does not support period strings beyond 10y.

    Examples:
        "5y"  → {"period": "5y"}
        "17y" → {"start": "2007-01-15"}   (today minus 17 years)
        "max" → {"period": "max"}
    """
    p = (period or "10y").strip().lower()
    if p in _YF_NATIVE_PERIODS:
        return {"period": p}
    if p.endswith("y"):
        try:
            years = int(p[:-1])
            start_dt = datetime.now() - timedelta(days=int(years * 365.25))
            return {"start": start_dt.strftime("%Y-%m-%d")}
        except ValueError:
            pass
    # Unrecognised format — fall back to passing as-is and let yfinance error
    return {"period": p}


def _min_bars_for_period(period: str) -> int:
    """Minimum number of bars required; short periods (e.g. 5d) need only 2 for prior/last."""
    period_lower = (period or "").strip().lower()
    if period_lower in ("1d", "5d", "1wk", "5day"):
        return 2
    return 50


def fetch_ohlcv(ticker: str, period: str = "5y") -> pd.Series | None:
    """
    Download adjusted close for ticker. Returns None if insufficient data or error.
    Supports extended periods (e.g. "17y") beyond yfinance's native "10y" cap.
    """
    if yf is None:
        raise ImportError("Install yfinance: pip install yfinance")

    min_bars = _min_bars_for_period(period)
    try:
        kwargs = _resolve_download_kwargs(period)
        data = yf.download(ticker, progress=False, threads=False, auto_adjust=True, **kwargs)
    except Exception:
        return None

    if data is None or data.empty or len(data) < min_bars:
        return None

    # yfinance: single ticker -> columns like Open, Close; multi -> MultiIndex
    close = None
    if isinstance(data.columns, pd.MultiIndex):
        close_col = data.get("Close")
        if close_col is not None:
            close = close_col.iloc[:, 0] if getattr(close_col, "ndim", 1) > 1 else close_col
    if close is None:
        for col in ("Adj Close", "Close"):
            if col in data.columns:
                close = data[col]
                break
        if close is None and len(data.columns) > 0:
            close = data.iloc[:, 0]
    if close is None:
        return None

    close = pd.Series(close, name="close").dropna()
    if len(close) < min_bars:
        return None
    return close


def fetch_ohlcv_safe(ticker: str, period: str = "5y") -> pd.Series | None:
    """Same as fetch_ohlcv but swallows errors and returns None."""
    try:
        return fetch_ohlcv(ticker, period)
    except Exception:
        return None


def fetch_ohlcv_monthly(ticker: str, period: str = "20y") -> pd.Series | None:
    """
    Fetch monthly-adjusted close for long-horizon risk (max drawdown, stress bear).
    Default 20y (Feb 2006-present) captures full 2008 crisis, 2020, 2022 and 2025.
    Uses interval=1mo to reduce noise and keep data size small.
    """
    if yf is None:
        return None
    try:
        kwargs = _resolve_download_kwargs(period)
        data = yf.download(ticker, interval="1mo", progress=False, threads=False, auto_adjust=True, **kwargs)
    except Exception:
        return None
    if data is None or data.empty or len(data) < 24:  # min ~2y monthly
        return None
    close = None
    if isinstance(data.columns, pd.MultiIndex):
        close_col = data.get("Close")
        if close_col is not None:
            close = close_col.iloc[:, 0] if getattr(close_col, "ndim", 1) > 1 else close_col
    if close is None:
        for col in ("Adj Close", "Close"):
            if col in data.columns:
                close = data[col]
                break
        if close is None and len(data.columns) > 0:
            close = data.iloc[:, 0]
    if close is None:
        return None
    close = pd.Series(close, name="close").dropna()
    return close if len(close) >= 24 else None


def fetch_ohlcv_with_volume(ticker: str, period: str = "5y") -> tuple[pd.Series | None, pd.Series | None]:
    """Fetch close and volume. Returns (close, volume) or (close, None) if volume unavailable."""
    if yf is None:
        return None, None
    try:
        kwargs = _resolve_download_kwargs(period)
        data = yf.download(ticker, progress=False, threads=False, auto_adjust=True, **kwargs)
    except Exception:
        return None, None
    if data is None or data.empty or len(data) < 20:
        return None, None
    close = None
    vol = None
    if isinstance(data.columns, pd.MultiIndex):
        close_col = data.get("Close")
        if close_col is not None:
            close = close_col.iloc[:, 0] if getattr(close_col, "ndim", 1) > 1 else close_col
        if "Volume" in data.columns:
            v = data["Volume"]
            vol = v.iloc[:, 0] if getattr(v, "ndim", 1) > 1 else v
    if close is None:
        for col in ("Adj Close", "Close"):
            if col in data.columns:
                close = data[col]
                break
        if close is None and len(data.columns) > 0:
            close = data.iloc[:, 0]
        vol = data["Volume"] if "Volume" in data.columns else None
    if close is None:
        return None, None
    close = pd.Series(close, name="close").dropna()
    if len(close) < 20:
        return None, None
    volume = pd.Series(vol, name="volume").dropna() if vol is not None and not vol.empty else None
    return close, volume


def fetch_yfinance_latest_prices(symbols: list[str]) -> dict[str, float]:
    """
    Fetch latest (delayed) quote from Yahoo for multiple symbols.
    Downloads one ticker at a time so one failure (e.g. MSFT) does not break the whole batch.
    Returns ticker -> last price. Use when FMP batch quote is not available (e.g. free plan).
    """
    if not yf or not symbols:
        return {}
    symbols = [s for s in symbols if s and isinstance(s, str)]
    if not symbols:
        return {}
    out: dict[str, float] = {}
    for sym in symbols:
        try:
            data = yf.download(
                sym,
                period="5d",
                progress=False,
                threads=False,
                auto_adjust=True,
            )
            if data is None or data.empty or len(data) == 0:
                logger.warning("[yfinance] Skipping %s: no data returned (latest price unavailable)", sym)
                continue
            # Single-ticker: columns are flat (Open, High, Low, Close, etc.)
            close_col = data.get("Close") if isinstance(data, pd.DataFrame) else None
            if close_col is None and isinstance(data, pd.DataFrame) and "Adj Close" in data.columns:
                close_col = data["Adj Close"]
            if close_col is not None and len(close_col) > 0:
                last = close_col.dropna()
                if len(last) > 0:
                    val = last.iloc[-1]
                    # Ensure scalar: yfinance can return Series in edge cases (e.g. AMZN), avoid "truth value of Series is ambiguous"
                    if hasattr(val, "ndim") and getattr(val, "ndim", 0) > 0 and hasattr(val, "iloc"):
                        val = val.iloc[-1] if len(val) > 0 else None
                    if val is not None:
                        try:
                            v = float(val)
                            if not (pd.isna(v) or v <= 0):
                                out[sym] = v
                            else:
                                logger.warning("[yfinance] Skipping %s: no valid close (latest price unavailable)", sym)
                        except (TypeError, ValueError):
                            logger.warning("[yfinance] Skipping %s: no valid close (latest price unavailable)", sym)
                    else:
                        logger.warning("[yfinance] Skipping %s: no valid close (latest price unavailable)", sym)
                else:
                    logger.warning("[yfinance] Skipping %s: no valid close (latest price unavailable)", sym)
            else:
                logger.warning("[yfinance] Skipping %s: no Close column (latest price unavailable)", sym)
        except Exception as e:
            logger.warning("[yfinance] Skipping %s: %s", sym, e)
            continue
    return out


def fetch_ohlcv_dataframe(ticker: str, period: str = "2y") -> pd.DataFrame | None:
    """
    Fetch OHLCV as a DataFrame with columns: close, high, low, volume.
    Required by pattern_signals.py for Bollinger Bands, 52-week low, volume climax.
    Returns None on error or insufficient data (< 60 bars).
    """
    if yf is None:
        return None
    try:
        kwargs = _resolve_download_kwargs(period)
        data = yf.download(ticker, progress=False, threads=False, auto_adjust=True, **kwargs)
    except Exception:
        return None
    if data is None or data.empty or len(data) < 60:
        return None

    # Normalise MultiIndex vs flat columns
    def _get_col(name: str) -> pd.Series | None:
        if isinstance(data.columns, pd.MultiIndex):
            col = data.get(name)
            if col is not None:
                return col.iloc[:, 0] if getattr(col, "ndim", 1) > 1 else col
            return None
        return data.get(name)

    close  = _get_col("Close")
    high   = _get_col("High")
    low    = _get_col("Low")
    volume = _get_col("Volume")

    if close is None:
        return None

    out = pd.DataFrame({"close": close})
    if high   is not None: out["high"]   = high
    if low    is not None: out["low"]    = low
    if volume is not None: out["volume"] = volume
    out = out.dropna(subset=["close"])
    return out if len(out) >= 60 else None


def fetch_ohlcv_with_config(ticker: str, period: str, config: dict | None) -> pd.Series | None:
    """Use FMP if api_key in config, else yfinance."""
    try:
        from .providers import fetch_ohlcv as fetch_provider
        return fetch_provider(ticker, period, config)
    except Exception:
        return fetch_ohlcv_safe(ticker, period)
