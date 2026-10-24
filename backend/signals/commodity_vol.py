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

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_DATE: str | None = None

_PERIOD = "1y"


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
    sym = _VOL_INDEX_BY_TICKER.get(str(ticker).upper())
    if not sym:
        return None

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _CACHE_DATE != today:
        _CACHE.clear()
        _CACHE_DATE = today
    if sym in _CACHE:
        cached = _CACHE[sym]
    else:
        cached = {"level": None, "percentile": None}
        try:
            from signals.fetcher import fetch_ohlcv_safe

            close = fetch_ohlcv_safe(sym, _PERIOD)
            if close is not None and len(close) > 0:
                closes = [float(x) for x in list(close.values)]
                cached = {
                    "level": round(closes[-1], 2),
                    "percentile": _vol_percentile(closes),
                }
        except Exception as e:
            logger.debug("commodity_vol %s: %s", sym, e)
        _CACHE[sym] = cached

    if cached["level"] is None:
        return None
    return {
        "symbol": sym,
        "level": cached["level"],
        "percentile": cached["percentile"],
        "regime": _vol_regime(cached["percentile"]),
    }
