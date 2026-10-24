"""
Commodity volatility regime: maps commodity ETFs to their CBOE vol index
(^GVZ gold, ^OVX oil) and computes the current 52-week percentile of that
index — the commodity equivalent of IV rank.

Why: commodity ETFs (~15% of the watchlist) score regime from the equity HMM,
which is the wrong market for them — gold follows gold vol, not SPY vol.
Fetches are per-UTC-day cached (one Yahoo pull per index per day).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import logging

logger = logging.getLogger(__name__)

# Ticker → CBOE vol index for its underlying asset.
# Only assets with a real published CBOE vol index are mapped.
_VOL_INDEX_BY_TICKER: dict[str, str] = {
    # Gold & gold-linked
    "GLD": "^GVZ", "SLV": "^GVZ", "IAU": "^GVZ", "GDX": "^GVZ", "GDXJ": "^GVZ",
    "GOLD": "^GVZ",
    # Metals/miners with gold-correlated vol
    "URA": "^GVZ", "URNM": "^GVZ", "COPX": "^GVZ",
    # Energy
    "USO": "^OVX", "UNG": "^OVX", "XLE": "^OVX",
}

# Tickers with NO published CBOE vol index (grains et al.) — fall back to the
# ETF's own realized vol, percentiled inside its own 1y range. Same regime
# semantics (calm/neutral/stress), symbol reported as "RV:{ticker}" so the
# gate detail reads "RV:WEAT calm (NNth pct)" instead of implying a CBOE index.
_REALIZED_VOL_TICKERS: set[str] = {"WEAT", "CORN"}

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_DATE: str | None = None

_PERIOD = "1y"
_REALIZED_VOL_WINDOW = 20  # trading days for the realized-vol estimate


def _vol_percentile(closes: list[float]) -> float | None:
    """Percentile of the last close within the 52-week range (0-100)."""
    if not closes or len(closes) < 40:
        return None
    window = closes[-252:] if len(closes) > 252 else closes
    cur = window[-1]
    lo, hi = min(window), max(window)
    if hi <= lo:
        return None
    return round(100.0 * (cur - lo) / (hi - lo), 1)


def _realized_vol_series(closes: list[float], window: int = _REALIZED_VOL_WINDOW) -> list[float]:
    """Annualized realized vol (%) from a rolling stdev of daily log returns."""
    import math

    rets = [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
        if closes[i - 1] > 0 and closes[i] > 0
    ]
    out: list[float] = []
    for i in range(window, len(rets) + 1):
        w = rets[i - window : i]
        mu = sum(w) / len(w)
        var = sum((r - mu) ** 2 for r in w) / (len(w) - 1)
        out.append(math.sqrt(var) * math.sqrt(252) * 100.0)
    return out


def _vol_regime(pct: float | None) -> str | None:
    if pct is None:
        return None
    if pct < 40:
        return "calm"      # supportive backdrop for commodity entries
    if pct > 70:
        return "stress"    # elevated fear in the commodity's own market
    return "neutral"


def commodity_vol_snapshot(ticker: str | None) -> dict[str, Any] | None:
    """
    For a commodity-ETF ticker return
      {symbol, level, percentile, regime}
    or None if the ticker isn't a mapped commodity ETF / data unavailable.
    """
    global _CACHE_DATE
    if not ticker:
        return None
    ticker_up = str(ticker).upper()
    sym = _VOL_INDEX_BY_TICKER.get(ticker_up)
    realized_fallback = sym is None and ticker_up in _REALIZED_VOL_TICKERS
    if sym is None and not realized_fallback:
        return None
    fetch_sym = ticker_up if realized_fallback else sym

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _CACHE_DATE != today:
        _CACHE.clear()
        _CACHE_DATE = today
    cache_key = f"RV:{ticker_up}" if realized_fallback else sym
    if cache_key in _CACHE:
        cached = _CACHE[cache_key]
    else:
        cached = {"level": None, "percentile": None}
        try:
            from signals.fetcher import fetch_ohlcv_safe

            close = fetch_ohlcv_safe(fetch_sym, _PERIOD)
            if close is not None and len(close) > 0:
                closes = [float(x) for x in list(close.values)]
                if realized_fallback:
                    # No CBOE index exists for grains — percentile the ETF's own
                    # 20d realized vol inside its trailing 1y path.
                    rv = _realized_vol_series(closes)
                    if rv:
                        cached = {
                            "level": round(rv[-1], 2),
                            "percentile": _vol_percentile(rv),
                        }
                else:
                    cached = {
                        "level": round(closes[-1], 2),
                        "percentile": _vol_percentile(closes),
                    }
        except Exception as e:
            logger.debug("commodity_vol %s: %s", fetch_sym, e)
        _CACHE[cache_key] = cached

    if cached["level"] is None:
        return None
    return {
        "symbol": cache_key,
        "level": cached["level"],
        "percentile": cached["percentile"],
        "regime": _vol_regime(cached["percentile"]),
    }
