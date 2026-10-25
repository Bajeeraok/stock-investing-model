"""
Pooled analysis of historical composite scores vs SPY (batch score backtest).

Input: one row per (as_of_date, ticker) sample with the live-parity composite score and
forward ticker / benchmark returns. Output: excess-vs-SPY by score bucket, broken down by
horizon, market regime, interpretation style, sector and year, plus rank IC per component.
Standard errors are clustered by date and corrected for overlapping forward windows.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from signals.alpha.excess import summarize_excess

BUCKETS = ((0, 30), (30, 50), (50, 70), (70, 100.01))
COMPONENTS = ("score", "score_raw", "trend_score", "rsi_contrib", "macd_contrib")


def bucket_of(score: float) -> str | None:
    if score is None or not math.isfinite(score):
        return None
    for lo, hi in BUCKETS:
        if lo <= score < hi:
            return f"{lo:.0f}-{min(hi, 100):.0f}"
    return None


def _overlap(horizon: int, step: int) -> int:
    return max(1, int(round(horizon / max(step, 1))))


def summarize_group(df: pd.DataFrame, horizon: int, step: int, cost_pct: float) -> dict[str, Any]:
    col = f"excess_{horizon}"
    sub = df[["as_of_date", col]].dropna()
    out = summarize_excess(
        sub[col].tolist(),
        cost_pct=cost_pct,
        prior_n=0.0,
        dates=sub["as_of_date"].tolist(),
        horizon_days=_overlap(horizon, step),
    )
    out.pop("shrunk_net_excess_pct", None)
    return out


def bucket_table(df: pd.DataFrame, horizon: int, step: int, cost_pct: float, by: str | None = None) -> dict:
    out: dict[str, Any] = {}
    groups = [("all", df)] if by is None else list(df.groupby(by))
    for g, gdf in groups:
        row = {"all": summarize_group(gdf, horizon, step, cost_pct)}
        for b, bdf in gdf.groupby("bucket"):
            row[b] = summarize_group(bdf, horizon, step, cost_pct)
        out[str(g)] = row
    return out


def rank_ic(df: pd.DataFrame, col: str, horizon: int, step: int, min_names: int = 10) -> dict[str, Any]:
    """Mean per-date Spearman IC of ``col`` vs forward excess, with overlap-corrected t."""
    target = f"excess_{horizon}"
    ics = []
    for _, g in df[["as_of_date", col, target]].dropna().groupby("as_of_date"):
        if len(g) < min_names or g[col].nunique() < 3:
            continue
        ic = g[col].rank().corr(g[target].rank())
        if ic == ic:
            ics.append(ic)
    n = len(ics)
    if n < 3:
        return {"n_dates": n, "ic_mean": None}
    arr = np.asarray(ics)
    n_eff = n / _overlap(horizon, step)
    sd = float(arr.std(ddof=1))
    t = float(arr.mean()) / (sd / math.sqrt(n_eff)) if n_eff > 1 and sd > 0 else None
    return {
        "n_dates": n,
        "n_eff": round(n_eff, 1),
        "ic_mean": round(float(arr.mean()), 4),
        "ic_t": round(t, 2) if t is not None else None,
        "ic_pos_pct": round(100.0 * float((arr > 0).mean()), 1),
    }


def analyze(df: pd.DataFrame, horizons: list[int], step: int, cost_pct: float) -> dict[str, Any]:
    df = df.copy()
    df["bucket"] = df["score"].map(bucket_of)
    df["year"] = pd.to_datetime(df["as_of_date"]).dt.year
    out: dict[str, Any] = {
        "n_samples": int(len(df)),
        "n_tickers": int(df["ticker"].nunique()),
        "date_range": [str(df["as_of_date"].min()), str(df["as_of_date"].max())],
        "step_days": step,
        "cost_pct": cost_pct,
        "horizons": {},
    }
    for h in horizons:
        if f"excess_{h}" not in df:
            continue
        hd = df.dropna(subset=[f"excess_{h}"])
        out["horizons"][str(h)] = {
            "buckets": bucket_table(hd, h, step, cost_pct)["all"],
            "by_regime": bucket_table(hd, h, step, cost_pct, by="spy_regime"),
            "by_style": bucket_table(hd, h, step, cost_pct, by="style"),
            "by_sector": bucket_table(hd, h, step, cost_pct, by="sector"),
            "by_year": bucket_table(hd, h, step, cost_pct, by="year"),
            "ic": {c: rank_ic(hd, c, h, step) for c in COMPONENTS if c in hd},
        }
    return out
