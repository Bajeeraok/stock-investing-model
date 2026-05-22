"""
Shared beta utilities — 1y daily return beta vs a benchmark (default SPY).
"""
from __future__ import annotations

import pandas as pd


def compute_beta(
    asset: pd.Series,
    benchmark: pd.Series | None,
    *,
    lookback_days: int = 252,
    min_obs: int = 30,
) -> float | None:
    """Beta of asset vs benchmark using aligned daily returns."""
    if benchmark is None or len(asset) < 63 or len(benchmark) < 63:
        return None
    aligned = pd.concat(
        [asset.rename("asset"), benchmark.rename("bm")], axis=1
    ).dropna()
    if len(aligned) < 63:
        return None
    rets = aligned.pct_change().dropna().tail(lookback_days)
    if len(rets) < min_obs:
        return None
    cov = rets["asset"].cov(rets["bm"])
    var = rets["bm"].var()
    return float(cov / var) if var != 0 else None


def compute_beta_from_returns(
    asset_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    lookback_days: int = 252,
    min_obs: int = 30,
) -> float | None:
    """Beta from pre-computed return series (aligned on index)."""
    aligned = pd.concat(
        [asset_returns.rename("asset"), benchmark_returns.rename("bm")], axis=1
    ).dropna()
    if len(aligned) < min_obs:
        return None
    rets = aligned.tail(lookback_days)
    if len(rets) < min_obs:
        return None
    cov = rets["asset"].cov(rets["bm"])
    var = rets["bm"].var()
    return float(cov / var) if var != 0 else None
