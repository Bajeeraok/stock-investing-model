"""
Correlation-aware sizing and simple historical VaR/CVaR from aligned return series.
Uses existing OHLCV fetcher (yfinance under the hood).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_correlation_matrix(
    tickers: list[str],
    lookback_days: int = 252,
    fetch_close=None,
) -> tuple[pd.DataFrame | None, str | None]:
    """
    Pairwise correlation of daily returns. fetch_close(ticker, period) -> Series or None.
    """
    if fetch_close is None:
        from signals.fetcher import fetch_ohlcv_safe

        def fetch_close(t: str, period: str) -> pd.Series | None:
            s = fetch_ohlcv_safe(t, period)
            return s

    period = "2y" if lookback_days <= 504 else "5y"

    prices: dict[str, pd.Series] = {}
    for t in tickers:
        sym = (t or "").upper().strip()
        if not sym:
            continue
        try:
            hist = fetch_close(sym, period)
            if hist is not None and len(hist) > 20:
                prices[sym] = hist
        except Exception as e:
            logger.debug("correlation skip %s: %s", sym, e)

    if len(prices) < 2:
        return None, "Need at least 2 tickers with history"
    df = pd.DataFrame(prices).pct_change().dropna()
    if len(df) < 30:
        return None, "Insufficient overlapping history"
    return df.corr(), None


def correlation_adjusted_sizing(
    tickers: list[str],
    base_sizes: dict[str, float],
    max_portfolio: float = 0.65,
    fetch_close=None,
) -> dict[str, float]:
    """
    Shrink each base Kelly fraction when average correlation to rest of book is high.
    """
    uniq = [t.upper() for t in tickers if t]
    if len(uniq) < 2:
        return {t: round(base_sizes.get(t, 0.25), 3) for t in uniq}

    corr, err = compute_correlation_matrix(uniq, fetch_close=fetch_close)
    if err or corr is None:
        return {t: round(base_sizes.get(t, 0.25), 3) for t in uniq}

    adjusted: dict[str, float] = {}
    for ticker in uniq:
        base = float(base_sizes.get(ticker, 0.25))
        others = [x for x in uniq if x != ticker]
        if not others:
            adjusted[ticker] = base
            continue
        avg_corr = float(
            np.mean([corr.loc[ticker, o] for o in others if o in corr.columns and ticker in corr.index])
        )
        correlation_penalty = max(0.0, (avg_corr - 0.3) / 0.7)
        adjusted[ticker] = base * (1.0 - correlation_penalty * 0.30)

    total = sum(adjusted.values())
    if total > max_portfolio and total > 0:
        factor = max_portfolio / total
        adjusted = {k: round(v * factor, 3) for k, v in adjusted.items()}
    else:
        adjusted = {k: round(v, 3) for k, v in adjusted.items()}
    return adjusted


def compute_var_cvar(
    tickers: list[str],
    weights: dict[str, float],
    confidence: float = 0.95,
    days: int = 10,
    fetch_close=None,
) -> dict[str, Any]:
    """
    Historical portfolio VaR/CVaR over `days` horizon (scaled from daily returns).
    """
    if fetch_close is None:
        from signals.fetcher import fetch_ohlcv_safe

        def fetch_close(t: str, period: str) -> pd.Series | None:
            return fetch_ohlcv_safe(t, period)

    period = "2y"
    rets: dict[str, pd.Series] = {}
    for t in tickers:
        sym = (t or "").upper().strip()
        if not sym:
            continue
        try:
            hist = fetch_close(sym, period)
            if hist is not None and len(hist) > 60:
                rets[sym] = hist.pct_change().dropna()
        except Exception as e:
            logger.debug("var skip %s: %s", sym, e)

    if len(rets) < 1:
        return {"error": "No return history"}

    df = pd.DataFrame(rets).dropna()
    if len(df) < 60:
        return {"error": "Insufficient overlapping returns"}

    w = np.array([float(weights.get(t, 0.0)) for t in df.columns])
    if w.sum() <= 0:
        return {"error": "Weights sum to zero"}
    w = w / w.sum()
    port_daily = (df.values * w).sum(axis=1)
    port_daily = pd.Series(port_daily)

    q = (1.0 - confidence) * 100.0
    var_daily = float(np.percentile(port_daily, q))
    scale = np.sqrt(float(days))
    var_h = var_daily * scale

    tail = port_daily[port_daily <= var_daily]
    cvar_daily = float(tail.mean()) if len(tail) else var_daily
    cvar_h = cvar_daily * scale

    return {
        "var_95_10day_pct": round(var_h * 100.0, 2),
        "cvar_95_10day_pct": round(cvar_h * 100.0, 2),
        "confidence": confidence,
        "horizon_days": days,
        "interpretation": (
            f"Historical {confidence:.0%} daily tail scaled to {days} sessions; "
            f"negative = loss in tail."
        ),
    }
