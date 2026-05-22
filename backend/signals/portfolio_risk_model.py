"""
Correlation-aware sizing and simple historical VaR/CVaR from aligned return series.
Uses existing OHLCV fetcher (yfinance under the hood).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from signals.beta_utils import compute_beta

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


def _beta_band(beta: float) -> dict[str, str]:
    if beta < 0.5:
        return {"label": "Defensive", "tone": "low"}
    if beta < 0.85:
        return {"label": "Below market", "tone": "moderate-low"}
    if beta <= 1.15:
        return {"label": "Market-like", "tone": "neutral"}
    if beta <= 1.45:
        return {"label": "Elevated", "tone": "moderate-high"}
    return {"label": "Aggressive", "tone": "high"}


def _beta_headline(beta: float) -> str:
    b = round(beta, 1)
    if abs(b - 1.0) < 0.05:
        return "Your portfolio moves about as much as the market (SPY ≈ 1.0×)."
    if b < 1.0:
        return f"Your portfolio moves {b:.1f}× the market — somewhat less volatile than SPY on average."
    return f"Your portfolio moves {b:.1f}× the market — more sensitive to broad market swings than SPY."


def compute_portfolio_beta_metrics(
    per_holding: list[dict],
    *,
    sector_allocation: list[dict] | None = None,
    benchmark: str = "SPY",
    lookback_days: int = 252,
    fetch_close=None,
) -> dict[str, Any]:
    """
    Per-holding, sector, and portfolio-weighted beta vs benchmark (default SPY).

    Portfolio beta = sum(weight_i × beta_i) over holdings with valid beta.
    """
    if fetch_close is None:
        from signals.fetcher import fetch_ohlcv_safe

        def fetch_close(t: str, period: str) -> pd.Series | None:
            return fetch_ohlcv_safe(t, period)

    consolidated: dict[str, dict] = {}
    for h in per_holding or []:
        t = (h.get("ticker") or "").upper().strip()
        if not t:
            continue
        val = float(h.get("value") or 0)
        pct = float(h.get("pct") or 0)
        if t in consolidated:
            consolidated[t]["value"] += val
            consolidated[t]["pct"] += pct
        else:
            consolidated[t] = {"ticker": t, "value": val, "pct": pct}

    holdings = [v for v in consolidated.values() if v.get("pct", 0) > 0]
    if not holdings:
        return {"error": "No holdings with allocation"}

    period = "2y" if lookback_days <= 504 else "5y"
    bm_sym = (benchmark or "SPY").upper()
    spy_close = fetch_close(bm_sym, period)
    if spy_close is None or len(spy_close) < 63:
        return {"error": f"Insufficient {bm_sym} history for beta"}

    sector_by_ticker: dict[str, str] = {}
    try:
        from signals.providers import get_sector_and_industry

        for h in holdings:
            t = h["ticker"]
            info = get_sector_and_industry(t) or {}
            sector_by_ticker[t] = (info.get("sector") or "Unknown").strip() or "Unknown"
    except Exception:
        for h in holdings:
            sector_by_ticker[h["ticker"]] = "Unknown"

    holding_rows: list[dict] = []
    sector_acc: dict[str, dict[str, float]] = {}

    for h in holdings:
        t = h["ticker"]
        w = h["pct"] / 100.0
        try:
            close = fetch_close(t, period)
        except Exception:
            close = None
        beta = compute_beta(close, spy_close, lookback_days=lookback_days) if close is not None else None
        row = {
            "ticker": t,
            "beta": round(beta, 2) if beta is not None else None,
            "weight_pct": round(h["pct"], 1),
            "sector": sector_by_ticker.get(t, "Unknown"),
        }
        if beta is not None:
            row["contribution"] = round(w * beta, 3)
        holding_rows.append(row)

        sec = row["sector"]
        if sec not in sector_acc:
            sector_acc[sec] = {"weight": 0.0, "beta_sum": 0.0}
        sector_acc[sec]["weight"] += h["pct"]
        if beta is not None:
            sector_acc[sec]["beta_sum"] += w * beta

    with_beta = [r for r in holding_rows if r.get("beta") is not None]
    covered_weight = sum(r["weight_pct"] for r in with_beta)
    portfolio_beta = None
    if with_beta and covered_weight > 0:
        portfolio_beta = round(
            sum((r["weight_pct"] / 100.0) * r["beta"] for r in with_beta)
            / (covered_weight / 100.0),
            2,
        )

    sector_rows = []
    for sec, acc in sorted(sector_acc.items(), key=lambda x: -x[1]["weight"]):
        sec_beta = None
        if acc["weight"] > 0 and acc["beta_sum"] > 0:
            sec_beta = round(acc["beta_sum"] / (acc["weight"] / 100.0), 2)
        sector_rows.append({
            "sector": sec,
            "beta": sec_beta,
            "weight_pct": round(acc["weight"], 1),
        })

    holding_rows.sort(key=lambda x: (-(x.get("contribution") or 0), -x["weight_pct"]))

    out: dict[str, Any] = {
        "benchmark": bm_sym,
        "portfolio_beta": portfolio_beta,
        "coverage_pct": round(covered_weight, 1),
        "holdings": holding_rows,
        "sectors": sector_rows,
        "lookback_days": lookback_days,
    }
    if portfolio_beta is not None:
        band = _beta_band(portfolio_beta)
        out["band"] = band["label"]
        out["band_tone"] = band["tone"]
        out["headline"] = _beta_headline(portfolio_beta)
    else:
        out["error"] = "Could not compute beta for any holding"
    return out
