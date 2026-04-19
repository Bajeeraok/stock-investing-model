"""
Rolling correlation vs macro proxies (GLD, UUP as USD, ^VIX) for retail badges.
Lightweight: daily closes, 60 trading days min overlap.
"""
from __future__ import annotations

import pandas as pd

from .fetcher import fetch_ohlcv_safe


def _aligned_returns(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series] | None:
    if a is None or b is None or len(a) < 30 or len(b) < 30:
        return None
    common = a.index.intersection(b.index)
    if len(common) < 30:
        return None
    ra = a.reindex(common).pct_change().dropna()
    rb = b.reindex(common).pct_change().dropna()
    c2 = ra.index.intersection(rb.index)
    if len(c2) < 30:
        return None
    return ra.loc[c2], rb.loc[c2]


def compute_cross_asset_sensitivity(
    ticker: str,
    *,
    window: int = 60,
    period: str = "2y",
) -> dict:
    """
    Returns {badges: list[str], correlations: dict[str, float | None]}.
    Badges: gold-sensitive, USD-sensitive, volatility-sensitive (|ρ| ≥ 0.25).
    """
    px = fetch_ohlcv_safe(ticker, period)
    gld = fetch_ohlcv_safe("GLD", period)
    uup = fetch_ohlcv_safe("UUP", period)
    vix = fetch_ohlcv_safe("^VIX", period)

    out: dict[str, float | None] = {"gld_60d": None, "uup_60d": None, "vix_60d": None}
    badges: list[str] = []

    def _corr_pair(t_ser: pd.Series, ref: pd.Series | None) -> float | None:
        if ref is None:
            return None
        pair = _aligned_returns(t_ser, ref)
        if pair is None:
            return None
        ra, rb = pair
        tail = min(window, len(ra), len(rb))
        if tail < 20:
            return None
        ra = ra.iloc[-tail:]
        rb = rb.iloc[-tail:]
        if len(ra) < 20:
            return None
        return float(ra.corr(rb))

    if px is not None:
        out["gld_60d"] = _corr_pair(px, gld)
        out["uup_60d"] = _corr_pair(px, uup)
        out["vix_60d"] = _corr_pair(px, vix)

    if out["gld_60d"] is not None and abs(out["gld_60d"]) >= 0.25:
        badges.append("gold-sensitive")
    if out["uup_60d"] is not None and abs(out["uup_60d"]) >= 0.25:
        badges.append("USD-sensitive")
    if out["vix_60d"] is not None and abs(out["vix_60d"]) >= 0.25:
        badges.append("volatility-sensitive")

    return {"badges": badges, "correlations": out}
