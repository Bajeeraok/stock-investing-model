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
    # Lock to adjusted close only: never mix raw close with adjusted (pro-site parity).
    if "adjClose" not in df.columns:
        return None
    return df["adjClose"].dropna()


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


# Sector -> SPDR ETF for industry benchmark
_SECTOR_ETF = {
    "technology": "XLK",
    "financial services": "XLF",
    "financials": "XLF",
    "healthcare": "XLV",
    "health care": "XLV",
    "consumer cyclical": "XLY",
    "consumer discretionary": "XLY",
    "consumer defensive": "XLP",
    "consumer staples": "XLP",
    "communication services": "XLC",
    "communications": "XLC",
    "energy": "XLE",
    "industrials": "XLI",
    "basic materials": "XLB",
    "materials": "XLB",
    "real estate": "XLRE",
    "utilities": "XLU",
}


def get_sector_and_industry(ticker: str) -> dict:
    """
    Get sector and industry for a ticker via yfinance.
    Returns {sector, industry, sector_etf, sector_etf_name}.
    Uses a fallback map for common ETFs and known yfinance misfires to avoid "Unknown".
    """
    if yf is None:
        return {}
    sym = (ticker or "").upper().split("-")[0]
    _FALLBACK = {
        "SPY": ("Market", "S&P 500 Index ETF", "SPY", "SPY (Market)"),
        "QQQ": ("Technology", "Nasdaq 100 Index ETF", "QQQ", "QQQ (Technology)"),
        "IWM": ("Small Caps", "Russell 2000 Index ETF", "IWM", "IWM (Small Caps)"),
        "DIA": ("Market", "Dow Jones Index ETF", "DIA", "DIA (Market)"),
        "GLD": ("Commodities", "Gold ETF", "GLD", "GLD (Commodities)"),
        "SLV": ("Commodities", "Silver ETF", "SLV", "SLV (Commodities)"),
    }
    if sym in _FALLBACK:
        sector, industry, sector_etf, sector_etf_name = _FALLBACK[sym]
        return {"sector": sector, "industry": industry, "sector_etf": sector_etf, "sector_etf_name": sector_etf_name}
    if sym in _ETFS:
        # Sector ETFs: label as their own sector rather than null
        return {"sector": "Market", "industry": "ETF", "sector_etf": "SPY", "sector_etf_name": "SPY (Market)"}
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        sector = (info.get("sector") or "").strip().lower()
        industry = (info.get("industry") or "").strip()
        if not sector:
            # Try pre-flight registry for special instruments / common misfires
            try:
                from signals.pre_flight.asset_classifier import ASSET_REGISTRY  # type: ignore
                meta = ASSET_REGISTRY.get(sym)
                if meta and getattr(meta, "sector", None):
                    return {
                        "sector": str(meta.sector),
                        "industry": industry or None,
                        "sector_etf": "SPY",
                        "sector_etf_name": "SPY (Market)",
                    }
            except Exception:
                pass
        sector_etf = _SECTOR_ETF.get(sector, "SPY") if sector else "SPY"
        return {
            "sector": sector.replace("-", " ").title() if sector else "Unknown",
            "industry": industry or None,
            "sector_etf": sector_etf,
            "sector_etf_name": f"{sector_etf} ({sector.replace('-', ' ').title()})" if sector else "SPY (Market)",
        }
    except Exception:
        return {"sector": "Unknown", "industry": None, "sector_etf": "SPY", "sector_etf_name": "SPY (Market)"}


def get_peers(ticker: str, config: dict | None = None) -> list[str]:
    """
    Get peer tickers (same industry/sector). Uses FMP if api_key, else yfinance fallback.
    Returns list of up to 8 peer tickers, excluding the ticker itself.
    """
    config = config or {}
    api_key = config.get("data", {}).get("fmp_api_key") or config.get("fmp_api_key")
    if api_key:
        peers = _get_peers_fmp(ticker, api_key)
        if peers:
            return peers[:8]
    return _get_peers_yfinance(ticker)


def _get_peers_fmp(ticker: str, api_key: str) -> list[str]:
    """FMP Stock Peers API - returns peers in same sector, similar market cap."""
    if urllib is None:
        return []
    url = f"https://financialmodelingprep.com/api/v4/stock_peers?symbol={ticker}&apikey={api_key}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as resp:
            data = _json.loads(resp.read().decode())
        if isinstance(data, list) and data and "peersList" in data[0]:
            peers = data[0].get("peersList", [])
            return [p for p in peers if p and p.upper() != ticker.upper()][:8]
    except Exception:
        pass
    return []


def _get_peers_yfinance(ticker: str) -> list[str]:
    """
    Fallback: use watchlist/config or static peer groups for common tickers.
    yfinance does not expose peers directly; we use a curated mapping.
    """
    _STATIC_PEERS = {
        "AAPL": ["MSFT", "GOOGL", "META", "AMZN", "NVDA"],
        "MSFT": ["AAPL", "GOOGL", "AMZN", "META", "NVDA"],
        "GOOGL": ["AAPL", "MSFT", "META", "AMZN"],
        "META": ["GOOGL", "AAPL", "AMZN", "SNAP", "PINS"],
        "AMZN": ["AAPL", "MSFT", "GOOGL", "WMT", "COST"],
        "NVDA": ["AMD", "INTC", "AVGO", "QCOM", "MSFT"],
        "TSLA": ["F", "GM", "RIVN", "LCID", "NIO"],
        "CRWD": ["PANW", "ZS", "FTNT", "OKTA", "S"],
        "LLY": ["JNJ", "PFE", "MRK", "ABBV", "UNH"],
        "PANW": ["CRWD", "FTNT", "ZS", "CHKP", "OKTA"],
        "AVGO": ["NVDA", "QCOM", "INTC", "AMD", "MU"],
        "BLK": ["SCHW", "GS", "MS", "JPM", "C"],
        "BABA": ["JD", "PDD", "TCEHY", "AMZN"],
    }
    return _STATIC_PEERS.get(ticker.upper(), [])[:6]


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
