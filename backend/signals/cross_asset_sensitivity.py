"""
Rolling correlation vs macro proxies (GLD, UUP as USD, ^VIX) for retail badges.
Lightweight: daily closes, 60 trading days min overlap.

Badges require a distinctive link vs the market, not a 60-day |ρ| ≥ 0.25 that
almost every equity prints in a risk-on tape (AMD tagged gold-sensitive).
"""
from __future__ import annotations

import pandas as pd

from .fetcher import fetch_ohlcv_safe

# Absolute |ρ| floor, plus excess vs SPY's |ρ| with the same proxy.
_GOLD_ABS, _GOLD_EXCESS = 0.40, 0.12
_USD_ABS, _USD_EXCESS = 0.40, 0.12
_VIX_ABS, _VIX_EXCESS = 0.55, 0.10


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


def badges_from_correlations(
    *,
    gld: float | None,
    uup: float | None,
    vix: float | None,
    spy_gld: float | None = None,
    spy_uup: float | None = None,
    spy_vix: float | None = None,
) -> list[str]:
    """Pure badge rules — ticker must track the proxy more than SPY does."""
    badges: list[str] = []

    def _ok(rho: float | None, spy_rho: float | None, abs_min: float, excess: float) -> bool:
        if rho is None or abs(rho) < abs_min:
            return False
        if spy_rho is None:
            return True
        return abs(rho) - abs(spy_rho) >= excess

    if _ok(gld, spy_gld, _GOLD_ABS, _GOLD_EXCESS):
        badges.append("gold-sensitive")
    if _ok(uup, spy_uup, _USD_ABS, _USD_EXCESS):
        badges.append("USD-sensitive")
    if _ok(vix, spy_vix, _VIX_ABS, _VIX_EXCESS):
        badges.append("volatility-sensitive")
    return badges


def compute_cross_asset_sensitivity(
    ticker: str,
    *,
    window: int = 60,
    period: str = "2y",
    close_series: pd.Series | None = None,
) -> dict:
    """
    Returns {badges: list[str], correlations: dict[str, float | None]}.
    """
    px = close_series if close_series is not None and len(close_series) >= 30 else fetch_ohlcv_safe(ticker, period)
    gld = fetch_ohlcv_safe("GLD", period)
    uup = fetch_ohlcv_safe("UUP", period)
    vix = fetch_ohlcv_safe("^VIX", period)
    spy = fetch_ohlcv_safe("SPY", period)

    out: dict[str, float | None] = {
        "gld_60d": None, "uup_60d": None, "vix_60d": None,
        "spy_gld_60d": None, "spy_uup_60d": None, "spy_vix_60d": None,
    }

    def _corr_pair(t_ser: pd.Series | None, ref: pd.Series | None) -> float | None:
        if t_ser is None or ref is None:
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
    if spy is not None:
        out["spy_gld_60d"] = _corr_pair(spy, gld)
        out["spy_uup_60d"] = _corr_pair(spy, uup)
        out["spy_vix_60d"] = _corr_pair(spy, vix)

    badges = badges_from_correlations(
        gld=out["gld_60d"],
        uup=out["uup_60d"],
        vix=out["vix_60d"],
        spy_gld=out["spy_gld_60d"],
        spy_uup=out["spy_uup_60d"],
        spy_vix=out["spy_vix_60d"],
    )
    return {"badges": badges, "correlations": out}
