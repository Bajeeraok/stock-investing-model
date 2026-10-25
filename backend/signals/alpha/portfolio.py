"""
Rank-and-pick portfolio construction for the pooled alpha model.

Ranks the universe by calibrated P(beat SPY), keeps the top names subject to a minimum
probability, a per-sector cap and a pairwise-correlation cap, weights by inverse
volatility, then scales gross exposure so the portfolio's ex-ante volatility is at most
``target_vol`` (remainder stays in cash/SPY).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def rank_and_pick(
    scores: pd.DataFrame,
    returns: pd.DataFrame | None = None,
    *,
    prob_col: str = "p_beat_short",
    sector_of: dict[str, str] | None = None,
    max_names: int = 15,
    min_prob: float = 0.5,
    max_per_sector: int = 3,
    max_pair_corr: float = 0.85,
    target_vol: float = 0.15,
    max_weight: float = 0.10,
    lookback: int = 126,
) -> dict[str, Any]:
    """
    ``scores``: index = ticker, needs ``prob_col``. ``returns``: daily returns, columns =
    tickers (used for vol / correlation). Returns picks with weights and diagnostics.
    """
    s = scores.dropna(subset=[prob_col]).sort_values(prob_col, ascending=False)
    s = s[s[prob_col] >= min_prob]
    rets = returns.tail(lookback) if returns is not None else None
    corr = rets.corr() if rets is not None else None
    picked: list[str] = []
    per_sector: dict[str, int] = {}
    skipped: dict[str, str] = {}
    for tk in s.index:
        if len(picked) >= max_names:
            break
        sec = (sector_of or {}).get(tk) or "Unknown"
        if per_sector.get(sec, 0) >= max_per_sector:
            skipped[tk] = f"sector cap ({sec})"
            continue
        if corr is not None and tk in corr.columns and picked:
            cmax = corr.loc[tk, [p for p in picked if p in corr.columns]].max()
            if pd.notna(cmax) and cmax > max_pair_corr:
                skipped[tk] = f"corr {cmax:.2f} > {max_pair_corr}"
                continue
        picked.append(tk)
        per_sector[sec] = per_sector.get(sec, 0) + 1
    if not picked:
        return {"picks": [], "gross_exposure": 0.0, "skipped": skipped, "ex_ante_vol": 0.0}

    if rets is not None and set(picked) <= set(rets.columns):
        vol = rets[picked].std() * np.sqrt(252)
        vol = vol.replace(0, np.nan).fillna(vol.median() if vol.notna().any() else 0.3)
    else:
        vol = pd.Series(0.3, index=picked)
    w = (1.0 / vol) / (1.0 / vol).sum()
    for _ in range(10):  # cap and redistribute
        over = w > max_weight
        if not over.any():
            break
        excess = (w[over] - max_weight).sum()
        w[over] = max_weight
        under = ~over
        if not under.any():
            break
        w[under] += excess * w[under] / w[under].sum()
    if rets is not None and set(picked) <= set(rets.columns):
        cov = rets[picked].cov().to_numpy() * 252
        ex_vol = float(np.sqrt(w.to_numpy() @ cov @ w.to_numpy()))
    else:
        ex_vol = float((w * vol).sum())
    scale = min(1.0, target_vol / ex_vol) if ex_vol > 0 else 1.0
    w = w * scale
    return {
        "picks": [
            {"ticker": tk, "weight": round(float(w[tk]), 4), "prob": round(float(s.loc[tk, prob_col]), 4),
             "sector": (sector_of or {}).get(tk) or "Unknown", "vol": round(float(vol[tk]), 4)}
            for tk in picked
        ],
        "gross_exposure": round(float(w.sum()), 4),
        "cash_or_index_weight": round(1 - float(w.sum()), 4),
        "ex_ante_vol": round(ex_vol * scale, 4),
        "skipped": skipped,
    }
