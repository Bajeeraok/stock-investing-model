"""
Fetch daily OHLCV. Handles missing data and short history.

Extended period support:
  yfinance only accepts period strings up to "10y". For longer histories
  (e.g. "17y" to capture 2007-2024 including the financial crisis),
  _resolve_download_kwargs() converts "Ny" where N > 10 into a start= date.
  This means "17y", "16y", "15y" all work transparently.

In-process OHLCV cache:
  Daily bar history doesn't change intraday.  A short TTL (10 min by default,
  overridden via OHLCV_CACHE_TTL_SECONDS env var) deduplicates repeated calls
  for the same ticker+period within a single dashboard refresh or signal run.
  SPY/VIX are the most-fetched tickers and benefit most from this.
  Cache is per-process (not shared between workers); Redis is not required.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import NamedTuple

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)

# yfinance logs HTTP 401 at ERROR before retry succeeds — keep our logs readable.
logging.getLogger("yfinance").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# In-process OHLCV cache — deduplicates repeated fetches within a single run
# ---------------------------------------------------------------------------

def _ohlcv_cache_ttl() -> int:
    """TTL in seconds. Override via OHLCV_CACHE_TTL_SECONDS env var (60–3600)."""
    raw = os.environ.get("OHLCV_CACHE_TTL_SECONDS", "").strip()
    if raw:
        try:
            return max(60, min(3600, int(raw)))
        except ValueError:
            pass
    return 600  # 10 min default


class _CacheEntry(NamedTuple):
    value: object  # pd.Series or pd.DataFrame or None
    ts: float


_ohlcv_lock = threading.Lock()
_ohlcv_store: dict[str, _CacheEntry] = {}


def _cache_get(key: str) -> tuple[bool, object]:
    with _ohlcv_lock:
        entry = _ohlcv_store.get(key)
    if entry is None:
        return False, None
    if time.monotonic() - entry.ts > _ohlcv_cache_ttl():
        return False, None
    return True, entry.value


def _cache_set(key: str, value: object) -> None:
    with _ohlcv_lock:
        _ohlcv_store[key] = _CacheEntry(value=value, ts=time.monotonic())


def _ohlcv_key(ticker: str, period: str, kind: str = "close") -> str:
    return f"{kind}:{ticker.upper()}:{period}"


# ---------------------------------------------------------------------------
# Data-quality helpers — stale-bar detection + price sanity gate
# ---------------------------------------------------------------------------

def _business_days_since(last_date: "pd.Timestamp | datetime") -> int:
    """Approximate business days between last_date and today (tz-naive)."""
    import pandas as _pd
    today = _pd.Timestamp.now().normalize()
    ts = _pd.Timestamp(last_date)
    # Normalise to tz-naive so bdate_range comparison is always consistent
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    ld = ts.normalize()
    if ld >= today:
        return 0
    try:
        bdays = len(_pd.bdate_range(ld, today)) - 1
        return max(0, bdays)
    except Exception:
        return int((today - ld).days)


def check_ohlcv_quality(
    close: "pd.Series",
    ticker: str = "",
    *,
    stale_threshold_bdays: int = 3,
    spike_threshold_pct: float = 25.0,
) -> dict:
    """
    Run basic data-quality checks on a close price series.

    Returns a dict:
      {
        "ok": bool,
        "warnings": list[str],   # non-empty when quality issues found
        "stale": bool,           # latest bar is >stale_threshold_bdays business days old
        "price_spike": bool,     # last bar moved >spike_threshold_pct vs prior
        "last_bar_date": str,    # ISO date of last bar
      }
    """
    warnings: list[str] = []
    stale = False
    spike = False
    last_bar_date = ""

    if close is None or len(close) < 2:
        return {"ok": False, "warnings": ["Insufficient data"], "stale": False, "price_spike": False, "last_bar_date": ""}

    try:
        last_idx = close.index[-1]
        last_bar_date = str(last_idx.date()) if hasattr(last_idx, "date") else str(last_idx)[:10]
        bdays = _business_days_since(last_idx)
        if bdays >= stale_threshold_bdays:
            stale = True
            warnings.append(
                f"{ticker or 'ticker'}: last bar {last_bar_date} is {bdays} business days old — possible data delay"
            )
    except Exception:
        pass

    try:
        last_price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2])
        if prev_price > 0:
            move_pct = abs(last_price - prev_price) / prev_price * 100.0
            if move_pct >= spike_threshold_pct:
                spike = True
                warnings.append(
                    f"{ticker or 'ticker'}: last bar moved {move_pct:.1f}% vs prior close "
                    f"(possible unadjusted split or data error)"
                )
    except Exception:
        pass

    return {
        "ok": len(warnings) == 0,
        "warnings": warnings,
        "stale": stale,
        "price_spike": spike,
        "last_bar_date": last_bar_date,
    }


# Major US index ETFs: use Ticker.history() (single ticker), not yf.download(), to avoid
# MultiIndex column binding bugs. Daily adjusted Close, regular hours only.
_INDEX_ETF_YF = frozenset({"SPY", "QQQ", "DIA", "IWM"})

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


def _is_yahoo_auth_error(exc: BaseException | str) -> bool:
    s = str(exc)
    return (
        "401" in s
        or "Invalid Crumb" in s
        or "Invalid Cookie" in s
        or "Unauthorized" in s
    )


def _clear_yfinance_crumb() -> None:
    """Force yfinance to fetch a fresh Yahoo cookie + crumb on the next request."""
    if yf is None:
        return
    try:
        from yfinance.data import YfData

        inst = YfData()
        inst._crumb = None
        inst._cookie = None
    except Exception:
        pass
    try:
        import yfinance.base as _yfbase  # type: ignore

        if hasattr(_yfbase, "_DFS"):
            _yfbase._DFS.clear()
    except Exception:
        pass
    try:
        from yfinance import shared as _yfshared  # type: ignore

        if hasattr(_yfshared, "_CACHE"):
            _yfshared._CACHE.clear()
    except Exception:
        pass


def _download_with_crumb_retry(tickers, **kwargs) -> "pd.DataFrame | None":
    """
    yfinance wrapper that retries once on 401 Invalid Crumb by clearing
    the session cache and forcing a fresh crumb fetch.
    Yahoo Finance rotates crumbs periodically; a stale crumb causes 401s
    that resolve automatically on the next request after a session reset.
    """
    if yf is None:
        return None
    threads = kwargs.pop("threads", False)
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            if attempt > 0:
                _clear_yfinance_crumb()
            result = yf.download(
                tickers,
                progress=False,
                threads=threads,
                auto_adjust=True,
                **kwargs,
            )
            if result is not None and not getattr(result, "empty", True):
                return result
            return result
        except Exception as e:
            last_err = e
            if attempt == 0 and _is_yahoo_auth_error(e):
                logger.info("[yfinance] auth error on download — refreshing crumb and retrying once")
                continue
            logger.debug("[yfinance] download failed: %s", e)
            return None
    if last_err and _is_yahoo_auth_error(last_err):
        logger.warning("[yfinance] download still unauthorized after crumb refresh")
    return None


def _history_with_crumb_retry(sym: str, **history_kw) -> "pd.DataFrame | None":
    """Ticker.history with one crumb-refresh retry on Yahoo 401."""
    if yf is None:
        return None
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            if attempt > 0:
                _clear_yfinance_crumb()
            hist = yf.Ticker(sym).history(**history_kw)
            if hist is not None and not hist.empty:
                return hist
            return hist
        except Exception as e:
            last_err = e
            if attempt == 0 and _is_yahoo_auth_error(e):
                logger.info("[yfinance] auth error on history %s — refreshing crumb and retrying once", sym)
                continue
            logger.debug("[yfinance] history failed %s: %s", sym, e)
            return None
    if last_err and _is_yahoo_auth_error(last_err):
        logger.warning("[yfinance] history still unauthorized for %s after crumb refresh", sym)
    return None


def _min_bars_for_period(period: str) -> int:
    """Minimum number of bars required; short periods (e.g. 5d) need only 2 for prior/last."""
    period_lower = (period or "").strip().lower()
    if period_lower in ("1d", "5d", "1wk", "5day"):
        return 2
    return 50


def _history_kwargs_from_period(period: str) -> dict:
    """Map our period string to yfinance Ticker.history(period=...) or history(start=...)."""
    kwargs = _resolve_download_kwargs(period)
    if "period" in kwargs:
        return {"period": kwargs["period"]}
    if "start" in kwargs:
        return {"start": kwargs["start"]}
    return {"period": "5y"}


def _fetch_index_etf_history_frame(sym: str, period: str) -> pd.DataFrame | None:
    """
    Daily OHLCV for index ETFs via Ticker.history (adjusted Close), regular hours only.
    """
    if yf is None:
        return None
    try:
        hkw = _history_kwargs_from_period(period)
        hist = _history_with_crumb_retry(
            sym,
            auto_adjust=True,
            prepost=False,
            repair=True,
            interval="1d",
            **hkw,
        )
        if hist is None or hist.empty or "Close" not in hist.columns:
            return None
        return hist.dropna(subset=["Close"])
    except Exception as e:
        logger.debug("[yfinance] index ETF history frame failed %s: %s", sym, e)
        return None


def _fetch_index_etf_via_ticker_history(ticker: str, period: str) -> tuple[pd.Series | None, pd.Series | None]:
    """
    Single-ticker yfinance path for SPY/QQQ/DIA/IWM: Ticker.history (adjusted Close), prepost=False.
    Returns (close, volume) or (None, None).
    """
    sym = (ticker or "").strip().upper()
    if sym not in _INDEX_ETF_YF:
        return None, None
    if yf is None:
        return None, None
    min_bars = _min_bars_for_period(period)
    try:
        hist = _fetch_index_etf_history_frame(sym, period)
        if hist is None or len(hist) < min_bars:
            return None, None
        close = pd.Series(hist["Close"], name="close")
        vol = None
        if "Volume" in hist.columns:
            vol = pd.Series(hist["Volume"], name="volume")
        return close, vol
    except Exception as e:
        logger.debug("[yfinance] index ETF history failed %s: %s", sym, e)
        return None, None


def _fetch_index_etf_ohlcv_dataframe(ticker: str, period: str, min_bars: int = 60) -> pd.DataFrame | None:
    """OHLCV DataFrame for SPY/QQQ/DIA/IWM via Ticker.history (same Close series as fetch_ohlcv)."""
    sym = (ticker or "").strip().upper()
    if sym not in _INDEX_ETF_YF:
        return None
    try:
        hist = _fetch_index_etf_history_frame(sym, period)
        if hist is None or len(hist) < min_bars:
            return None
        out = pd.DataFrame({"close": hist["Close"]})
        if "High" in hist.columns:
            out["high"] = hist["High"]
        if "Low" in hist.columns:
            out["low"] = hist["Low"]
        if "Volume" in hist.columns:
            out["volume"] = hist["Volume"]
        return out
    except Exception as e:
        logger.debug("[yfinance] index ETF OHLCV dataframe failed %s: %s", sym, e)
        return None


def fetch_ohlcv(ticker: str, period: str = "5y") -> pd.Series | None:
    """
    Download adjusted close for ticker. Returns None if insufficient data or error.
    Supports extended periods (e.g. "17y") beyond yfinance's native "10y" cap.
    """
    if yf is None:
        raise ImportError("Install yfinance: pip install yfinance")

    min_bars = _min_bars_for_period(period)
    c_hist, _ = _fetch_index_etf_via_ticker_history(ticker, period)
    if c_hist is not None and len(c_hist) >= min_bars:
        return c_hist

    kwargs = _resolve_download_kwargs(period)
    data = _download_with_crumb_retry(ticker, **kwargs)

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
    """Same as fetch_ohlcv but swallows errors and returns None.

    Results are cached in-process for _ohlcv_cache_ttl() seconds (default 10 min)
    to avoid redundant downloads when multiple callers request the same ticker+period
    within a single dashboard refresh (e.g. SPY fetched for regime, HMM, and ticker detail).

    Quality checks (stale bar, price spike) run on first fetch and log warnings so
    data issues surface in the application log without blocking signal computation.
    """
    key = _ohlcv_key(ticker, period, "close")
    hit, cached = _cache_get(key)
    if hit:
        return cached  # type: ignore[return-value]
    try:
        result = fetch_ohlcv(ticker, period)
    except Exception:
        result = None
    if result is not None:
        qc = check_ohlcv_quality(result, ticker=ticker)
        for w in qc.get("warnings") or []:
            logger.warning("[ohlcv_quality] %s", w)
    _cache_set(key, result)
    return result


def fetch_ohlcv_monthly(ticker: str, period: str = "20y") -> pd.Series | None:
    """
    Fetch monthly-adjusted close for long-horizon risk (max drawdown, stress bear).
    Default 20y (Feb 2006-present) captures full 2008 crisis, 2020, 2022 and 2025.
    Uses interval=1mo to reduce noise and keep data size small.
    """
    if yf is None:
        return None
    kwargs = _resolve_download_kwargs(period)
    data = _download_with_crumb_retry(ticker, interval="1mo", **kwargs)
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
    """Fetch close and volume. Returns (close, volume) or (close, None) if volume unavailable.

    Results are cached in-process for _ohlcv_cache_ttl() seconds.
    """
    key = _ohlcv_key(ticker, period, "close_vol")
    hit, cached = _cache_get(key)
    if hit:
        return cached  # type: ignore[return-value]

    if yf is None:
        _cache_set(key, (None, None))
        return None, None

    c_hist, v_hist = _fetch_index_etf_via_ticker_history(ticker, period)
    if c_hist is not None and len(c_hist) >= _min_bars_for_period(period):
        result = (c_hist, v_hist)
        _cache_set(key, result)
        return result

    kwargs = _resolve_download_kwargs(period)
    data = _download_with_crumb_retry(ticker, **kwargs)
    if data is None or data.empty or len(data) < 20:
        _cache_set(key, (None, None))
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
        _cache_set(key, (None, None))
        return None, None
    close = pd.Series(close, name="close").dropna()
    if len(close) < 20:
        _cache_set(key, (None, None))
        return None, None
    volume = pd.Series(vol, name="volume").dropna() if vol is not None and not vol.empty else None
    result = (close, volume)
    _cache_set(key, result)
    return result


def fetch_yfinance_latest_prices(symbols: list[str]) -> dict[str, float]:
    """
    Fetch latest (delayed) quote from Yahoo for multiple symbols via a single batch download.

    Uses yf.download(tickers=...) for all non-index-ETF symbols in one call, then
    falls back to serial Ticker.history for the index ETFs (SPY/QQQ/DIA/IWM) which
    need the dedicated path to avoid MultiIndex quirks on single tickers.

    Returns ticker -> last close price. Skips symbols that fail; never raises.
    """
    if not yf or not symbols:
        return {}
    symbols = [s.strip().upper() for s in symbols if s and isinstance(s, str)]
    if not symbols:
        return {}

    out: dict[str, float] = {}
    index_syms = [s for s in symbols if s in _INDEX_ETF_YF]
    batch_syms = [s for s in symbols if s not in _INDEX_ETF_YF]

    # --- Index ETFs via Ticker.history (avoids MultiIndex edge cases) ---
    for sym in index_syms:
        try:
            hist = _fetch_index_etf_history_frame(sym, "5d")
            if hist is None or hist.empty or "Close" not in hist.columns:
                logger.warning("[yfinance] Skipping %s: no data (latest price unavailable)", sym)
                continue
            last = hist["Close"].dropna()
            if len(last) == 0:
                logger.warning("[yfinance] Skipping %s: empty close (latest price unavailable)", sym)
                continue
            val = float(last.iloc[-1])
            if not (pd.isna(val) or val <= 0):
                out[sym] = val
            else:
                logger.warning("[yfinance] Skipping %s: invalid close value (latest price unavailable)", sym)
        except Exception as e:
            logger.warning("[yfinance] Skipping %s: %s", sym, e)

    # --- All other tickers: single batch download ---
    if batch_syms:
        try:
            data = _download_with_crumb_retry(
                tickers=" ".join(batch_syms),
                period="5d",
                threads=True,
                group_by="ticker",
            )
            if data is None or data.empty:
                logger.warning("[yfinance] batch download returned no data for %d symbols", len(batch_syms))
                return out

            for sym in batch_syms:
                try:
                    close_col = None
                    if isinstance(data.columns, pd.MultiIndex):
                        if (sym, "Close") in data.columns:
                            close_col = data[(sym, "Close")]
                        elif (sym, "Adj Close") in data.columns:
                            close_col = data[(sym, "Adj Close")]
                    else:
                        # Single-ticker batch — columns are flat
                        for col in ("Close", "Adj Close"):
                            if col in data.columns:
                                close_col = data[col]
                                break
                    if close_col is None or (hasattr(close_col, "empty") and close_col.empty):
                        logger.warning("[yfinance] Skipping %s: no Close column in batch", sym)
                        continue
                    last = close_col.dropna()
                    if len(last) == 0:
                        logger.warning("[yfinance] Skipping %s: empty close in batch", sym)
                        continue
                    val = last.iloc[-1]
                    # Guard against yfinance returning a Series instead of scalar in edge cases
                    if hasattr(val, "ndim") and getattr(val, "ndim", 0) > 0 and hasattr(val, "iloc"):
                        val = val.iloc[-1] if len(val) > 0 else None
                    if val is None:
                        logger.warning("[yfinance] Skipping %s: None value in batch", sym)
                        continue
                    v = float(val)
                    if not (pd.isna(v) or v <= 0):
                        out[sym] = v
                    else:
                        logger.warning("[yfinance] Skipping %s: invalid close in batch", sym)
                except Exception as e:
                    logger.warning("[yfinance] Skipping %s in batch: %s", sym, e)
        except Exception as e:
            logger.warning("[yfinance] batch download failed (%d symbols): %s", len(batch_syms), e)
            # Graceful degradation: try serial for the remaining symbols not yet in out
            for sym in batch_syms:
                if sym in out:
                    continue
                try:
                    data_s = _download_with_crumb_retry(sym, period="5d", threads=False)
                    if data_s is None or data_s.empty:
                        continue
                    for col in ("Close", "Adj Close"):
                        if col in data_s.columns:
                            last = data_s[col].dropna()
                            if len(last) > 0:
                                v = float(last.iloc[-1])
                                if not (pd.isna(v) or v <= 0):
                                    out[sym] = v
                            break
                except Exception:
                    pass

    return out


def fetch_ohlcv_dataframe(ticker: str, period: str = "2y") -> pd.DataFrame | None:
    """
    Fetch OHLCV as a DataFrame with columns: close, high, low, volume.
    Required by pattern_signals.py for Bollinger Bands, 52-week low, volume climax.
    Returns None on error or insufficient data (< 60 bars).

    Results are cached in-process for _ohlcv_cache_ttl() seconds.
    """
    key = _ohlcv_key(ticker, period, "df")
    hit, cached = _cache_get(key)
    if hit:
        return cached  # type: ignore[return-value]

    if yf is None:
        _cache_set(key, None)
        return None
    idx_df = _fetch_index_etf_ohlcv_dataframe(ticker, period, min_bars=60)
    if idx_df is not None:
        _cache_set(key, idx_df)
        return idx_df
    kwargs = _resolve_download_kwargs(period)
    data = _download_with_crumb_retry(ticker, **kwargs)
    if data is None or data.empty or len(data) < 60:
        _cache_set(key, None)
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
        _cache_set(key, None)
        return None

    out = pd.DataFrame({"close": close})
    if high   is not None: out["high"]   = high
    if low    is not None: out["low"]    = low
    if volume is not None: out["volume"] = volume
    out = out.dropna(subset=["close"])
    result_df = out if len(out) >= 60 else None
    _cache_set(key, result_df)
    return result_df


def fetch_ohlcv_with_config(ticker: str, period: str, config: dict | None) -> pd.Series | None:
    """Use FMP if api_key in config, else yfinance."""
    try:
        from .providers import fetch_ohlcv as fetch_provider
        return fetch_provider(ticker, period, config)
    except Exception:
        return fetch_ohlcv_safe(ticker, period)


def fetch_ohlcv_close_and_volume(
    ticker: str, period: str = "5y", config: dict | None = None
) -> tuple[pd.Series | None, pd.Series | None]:
    """
    FMP adjClose + volume (same response) when api_key in config; else (None, None).
    Caller should fall back to fetch_ohlcv_with_volume / fetch_ohlcv_safe.
    """
    try:
        from .providers import fetch_ohlcv_close_and_volume as _f
        return _f(ticker, period, config)
    except Exception:
        return None, None
