"""Forward labels: excess return vs benchmark and triple-barrier (target before stop)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def forward_return(close: pd.Series, horizon: int) -> pd.Series:
    return close.shift(-horizon) / close - 1.0


def forward_excess_return(close: pd.Series, bench_close: pd.Series, horizon: int) -> pd.Series:
    """Ticker forward return minus benchmark forward return over the same bars (fraction)."""
    b = bench_close.reindex(close.index).ffill()
    return forward_return(close, horizon) - forward_return(b, horizon)


def excess_label(
    close: pd.Series, bench_close: pd.Series, horizon: int, cost: float = 0.003
) -> pd.Series:
    """1 if the ticker beats the benchmark by more than round-trip cost over ``horizon`` bars."""
    exc = forward_excess_return(close, bench_close, horizon)
    out = (exc > cost).astype(float)
    out[exc.isna()] = np.nan
    return out


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def triple_barrier_label(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    *,
    target_atr: float = 2.0,
    stop_atr: float = 1.0,
    atr_n: int = 14,
) -> pd.Series:
    """
    1 if the ATR target is touched before the ATR stop within ``horizon`` bars, else 0.
    A bar that touches both counts as stop (conservative). Last ``horizon`` bars are NaN.
    """
    a = atr(high, low, close, atr_n).to_numpy()
    c, h, lo = close.to_numpy(), high.to_numpy(), low.to_numpy()
    n = len(c)
    out = np.full(n, np.nan)
    for i in range(n - horizon):
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        tgt = c[i] + target_atr * a[i]
        stp = c[i] - stop_atr * a[i]
        res = 0.0
        for j in range(i + 1, i + horizon + 1):
            if lo[j] <= stp:
                break
            if h[j] >= tgt:
                res = 1.0
                break
        out[i] = res
    return pd.Series(out, index=close.index)
