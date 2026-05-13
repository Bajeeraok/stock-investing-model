"""
Performance attribution per holding — which positions contributed most to returns.

For each period (1m, 3m, 6m, YTD):
  contribution_pct = weight_i * return_i
  total portfolio return ≈ Σ contribution_pct

Brinson-style single-period attribution without benchmark decomposition.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_PERIODS = [
    ("1m", 21),
    ("3m", 63),
    ("6m", 126),
    ("YTD", None),
]


def _ytd_trading_days(close_series: pd.Series | None) -> int | None:
    """Number of trading days since Jan 1 of current year."""
    if close_series is None or close_series.empty:
        return None
    try:
        year_start = datetime(datetime.now().year, 1, 1)
        mask = close_series.index >= pd.Timestamp(year_start)
        return int(mask.sum()) - 1
    except Exception:
        return None


def compute_attribution(
    per_holding: list[dict],
    total_value: float,
    fetch_close=None,
) -> dict[str, Any]:
    """
    Per-holding return contribution across multiple periods.

    Returns {
      periods: {period_label: [{ticker, weight_pct, return_pct, contribution_pct}]},
      top_contributor: {ticker, contribution_pct, period},
      top_detractor: {ticker, contribution_pct, period},
    }
    """
    if fetch_close is None:
        from signals.fetcher import fetch_ohlcv_safe
        fetch_close = lambda t, p: fetch_ohlcv_safe(t, p)

    holdings = [
        (h["ticker"], h.get("value", 0) or 0, h.get("pct", 0) or 0)
        for h in per_holding
        if h.get("ticker") and h.get("value") and h.get("pct")
    ]

    if not holdings or total_value <= 0:
        return {"periods": {}, "top_contributor": None, "top_detractor": None}

    # Fetch 1y history for all (covers all periods)
    hist: dict[str, pd.Series | None] = {}
    for ticker, _, _ in holdings:
        try:
            hist[ticker] = fetch_close(ticker, "1y")
        except Exception:
            hist[ticker] = None

    periods_out: dict[str, list[dict]] = {}
    all_contributions: list[tuple[str, float, str]] = []

    for period_label, n_days in _PERIODS:
        rows: list[dict] = []
        portfolio_return = 0.0

        for ticker, value, weight_pct in holdings:
            series = hist.get(ticker)
            if series is None or len(series) < 10:
                rows.append({
                    "ticker": ticker,
                    "weight_pct": round(weight_pct, 1),
                    "return_pct": None,
                    "contribution_pct": None,
                })
                continue

            if period_label == "YTD":
                days = _ytd_trading_days(series)
            else:
                days = n_days

            if days is None or days <= 0 or len(series) < days + 1:
                rows.append({
                    "ticker": ticker,
                    "weight_pct": round(weight_pct, 1),
                    "return_pct": None,
                    "contribution_pct": None,
                })
                continue

            try:
                price_now = float(series.iloc[-1])
                price_then = float(series.iloc[-1 - days])
                if price_then <= 0:
                    raise ValueError
                ret = (price_now - price_then) / price_then * 100
                contribution = (weight_pct / 100) * ret
                portfolio_return += contribution

                rows.append({
                    "ticker": ticker,
                    "weight_pct": round(weight_pct, 1),
                    "return_pct": round(ret, 2),
                    "contribution_pct": round(contribution, 2),
                })
                all_contributions.append((ticker, contribution, period_label))
            except (IndexError, TypeError, ValueError, ZeroDivisionError):
                rows.append({
                    "ticker": ticker,
                    "weight_pct": round(weight_pct, 1),
                    "return_pct": None,
                    "contribution_pct": None,
                })

        rows.sort(key=lambda x: -(x.get("contribution_pct") or -999))
        periods_out[period_label] = rows

    # Top contributor / detractor across all periods
    top_contributor = None
    top_detractor = None
    if all_contributions:
        best = max(all_contributions, key=lambda x: x[1])
        worst = min(all_contributions, key=lambda x: x[1])
        if best[1] > 0:
            top_contributor = {"ticker": best[0], "contribution_pct": round(best[1], 2), "period": best[2]}
        if worst[1] < 0:
            top_detractor = {"ticker": worst[0], "contribution_pct": round(worst[1], 2), "period": worst[2]}

    return {
        "periods": periods_out,
        "top_contributor": top_contributor,
        "top_detractor": top_detractor,
    }
