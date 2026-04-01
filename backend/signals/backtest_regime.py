"""
Market regime labels for backtests (SPY vs SMA — coarse bull/bear).

Used for reporting only; does not change composite scores. Aligns with common
\"risk-on / risk-off\" storytelling; not a timing model.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def align_benchmark_to_index(benchmark_close: pd.Series, template_index: pd.DatetimeIndex) -> pd.Series:
    """Forward-fill benchmark prices onto the ticker's trading calendar."""
    s = benchmark_close.sort_index()
    return s.reindex(template_index).ffill()


def regime_label_at(
    aligned_spy: pd.Series,
    bar_index: int,
    ma_days: int = 200,
) -> str:
    """
    bull: close > SMA(ma_days) at bar; bear: below; neutral: within 0.1%;
    unknown: insufficient history or NaN.
    """
    if bar_index < ma_days or bar_index >= len(aligned_spy):
        return "unknown"
    sub = aligned_spy.iloc[: bar_index + 1]
    roll = sub.rolling(ma_days).mean()
    px = aligned_spy.iloc[bar_index]
    ma = roll.iloc[bar_index]
    try:
        px_f = float(px)
        ma_f = float(ma)
    except (TypeError, ValueError):
        return "unknown"
    if np.isnan(ma_f) or np.isnan(px_f):
        return "unknown"
    band = max(ma_f * 0.001, 1e-9)
    if px_f > ma_f + band:
        return "bull"
    if px_f < ma_f - band:
        return "bear"
    return "neutral"


def summarize_regime_distribution(
    aligned_spy: pd.Series,
    start_i: int,
    end_i_exclusive: int,
    ma_days: int,
) -> dict[str, Any]:
    """Fraction of bar indices in [start_i, end_i) that are bull / bear / neutral / unknown."""
    counts = {"bull": 0, "bear": 0, "neutral": 0, "unknown": 0}
    total = 0
    for i in range(start_i, min(end_i_exclusive, len(aligned_spy))):
        lab = regime_label_at(aligned_spy, i, ma_days)
        counts[lab] = counts.get(lab, 0) + 1
        total += 1
    if total == 0:
        return {
            "pct_trading_days_bull": None,
            "pct_trading_days_bear": None,
            "pct_trading_days_neutral": None,
            "bars_counted": 0,
        }
    return {
        "pct_trading_days_bull": round(100.0 * counts["bull"] / total, 1),
        "pct_trading_days_bear": round(100.0 * counts["bear"] / total, 1),
        "pct_trading_days_neutral": round(100.0 * counts["neutral"] / total, 1),
        "bars_counted": total,
    }


def aggregate_walk_forward_by_regime(
    windows: list[dict],
    horizon_months: int = 3,
) -> dict[str, dict[str, Any]]:
    """
    Group walk-forward windows by ``spy_regime``; average 3m (or chosen horizon) stats.
    """
    groups: dict[str, list[dict]] = {}
    for w in windows:
        r = w.get("spy_regime") or "unknown"
        groups.setdefault(r, []).append(w)

    out: dict[str, dict[str, Any]] = {}
    for reg, wins in groups.items():
        if not wins:
            continue
        hrs = [
            h
            for w in wins
            for h in [w.get("results", {}).get(horizon_months, {}).get("hit_rate")]
            if h is not None
        ]
        rets = [
            r
            for w in wins
            for r in [w.get("results", {}).get(horizon_months, {}).get("avg_return_pct")]
            if r is not None
        ]
        out[reg] = {
            "window_count": len(wins),
            "avg_hit_rate_pct": round(float(np.mean(hrs)), 1) if hrs else None,
            "avg_net_return_pct": round(float(np.mean(rets)), 2) if rets else None,
        }
    return out
