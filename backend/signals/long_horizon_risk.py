"""
Long-horizon risk metrics for bear/base/bull and stress-testing.
Uses 10-20y of monthly data to capture tail events (2008, 2020, gold cycles).
Separate from short-term signals to avoid noise in ATR/vol.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .fetcher import fetch_ohlcv_monthly

logger = logging.getLogger(__name__)


def compute_long_horizon_risk(ticker: str, period: str = "13y") -> dict | None:
    """
    Compute max drawdown, worst 3y return, and stress bear pct from monthly data.
    Returns None on insufficient data or error.
    """
    close = fetch_ohlcv_monthly(ticker, period)
    if close is None or len(close) < 36:  # min 3y monthly
        return None

    try:
        close = close.sort_index()
        last_price = float(close.iloc[-1])
        if last_price <= 0:
            return None

        # Max drawdown over full period
        cummax = close.cummax()
        drawdown = (close - cummax) / cummax.replace(0, np.nan)
        max_dd = float(drawdown.min())
        max_drawdown_pct = round(100 * max_dd, 1)

        # Rolling 3y (36 months) worst return
        returns_3y = close.pct_change(36).dropna()
        if len(returns_3y) < 12:
            worst_3y_return_pct = None
        else:
            worst_3y_return_pct = round(100 * float(returns_3y.min()), 1)

        # Stress bear: 20th percentile of rolling drawdowns (bad tail – how bad it gets in stress)
        rolling_high = close.rolling(36, min_periods=12).max()
        rolling_dd = (close - rolling_high) / rolling_high.replace(0, np.nan)
        rolling_dd = rolling_dd.dropna()
        if len(rolling_dd) < 12:
            stress_bear_pct = abs(max_dd) * 100
        else:
            stress_bear_pct = abs(float(np.percentile(rolling_dd, 20)))
        stress_bear_pct = round(stress_bear_pct, 1)

        return {
            "max_drawdown_pct": max_drawdown_pct,
            "worst_3y_return_pct": worst_3y_return_pct,
            "stress_bear_pct": stress_bear_pct,
            "period_years": int(period.replace("y", "")) if isinstance(period, str) and "y" in period else 13,
        }
    except Exception as e:
        logger.debug("long_horizon_risk %s: %s", ticker, e)
        return None
