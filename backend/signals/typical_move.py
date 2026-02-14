"""
Typical 1-day move range from realized volatility (20d/60d).
Optional high-vol regime when VIX or 20d vol is elevated.
"""
from __future__ import annotations

import pandas as pd

from .fetcher import fetch_ohlcv_safe


def _daily_vol(close: pd.Series, window: int) -> float | None:
    """Annualized vol from last `window` daily returns."""
    if close is None or len(close) < window + 1:
        return None
    ret = close.pct_change().dropna().iloc[-window:]
    if len(ret) < window // 2:
        return None
    std = float(ret.std())
    return std * (252 ** 0.5)


def typical_move_range(
    ticker: str,
    period: str = "3mo",
    window_1d: int = 20,
    window_60d: int = 60,
    high_vol_mult: float = 1.5,
) -> dict | None:
    """
    Typical 1-day range ±1σ (and optional high-vol range).
    Returns dict: typical_pct_1d, typical_pct_60d, high_vol_pct (if vol elevated), vol_regime.
    """
    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < window_1d + 5:
        return None

    vol_20 = _daily_vol(close, window_1d)
    vol_60 = _daily_vol(close, min(window_60d, len(close) - 1))
    if vol_20 is None:
        return None

    # 1-day σ in % (annual vol / sqrt(252))
    sigma_1d_pct = (vol_20 / (252 ** 0.5)) * 100
    sigma_60d_pct = (vol_60 / (252 ** 0.5)) * 100 if vol_60 else sigma_1d_pct

    # High-vol regime: 20d vol > 1.2x 60d vol or use a fixed threshold
    vol_regime = "Normal"
    high_vol_pct = None
    if vol_60 and vol_20 > vol_60 * 1.2:
        vol_regime = "Elevated"
        high_vol_pct = round(sigma_1d_pct * high_vol_mult, 2)

    return {
        "ticker": ticker,
        "typical_pct_1d": round(sigma_1d_pct, 2),
        "typical_pct_60d": round(sigma_60d_pct, 2),
        "high_vol_pct": high_vol_pct,
        "vol_regime": vol_regime,
    }


def typical_move_for_symbols(
    symbols: list[str],
    period: str = "3mo",
) -> list[dict]:
    """Batch typical move for SPY, QQQ, GLD, SLV (or custom list)."""
    default = ["SPY", "QQQ", "GLD", "SLV"]
    syms = symbols if symbols else default
    out = []
    for t in syms:
        r = typical_move_range(t, period=period)
        if r:
            out.append(r)
    return out
