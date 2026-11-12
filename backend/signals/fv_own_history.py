"""
Fair value from a stock's own P/E history: TTM adjusted EPS × its median trailing P/E over the
last N years. Used where sector P/E comps mislead (asset managers such as BLK trade at a lasting
premium to peers). Walk-forward check on BLK 2012–26: premium >10% over this FV → +2% next 12m vs
+14–25% otherwise (monthly, n=118).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

# Backtested tickers only; other asset managers stay on street consensus until checked.
OWN_HISTORY_PE_TICKERS: frozenset[str] = frozenset({"BLK"})
# Skip own-history FV when it disagrees with street consensus by more than this.
MAX_STREET_GAP = 0.35


def own_history_pe(eps_rows: list[dict[str, Any]], px: pd.Series, *, years: int = 5,
                   min_months: int = 36) -> dict[str, Any] | None:
    rep = [(r["date"], float(r["eps_actual"])) for r in eps_rows if r.get("eps_actual") is not None and r.get("date")]
    if len(rep) < 8 or px is None or px.empty:
        return None
    eps = pd.Series({pd.Timestamp(d): v for d, v in rep}).sort_index()
    ttm = eps.rolling(4).sum().dropna()
    if ttm.empty or ttm.iloc[-1] <= 0:
        return None
    p = px.copy()
    if getattr(p.index, "tz", None) is not None:
        p.index = p.index.tz_localize(None)
    m = p.resample("ME").last().dropna()
    pe = (m / ttm.reindex(m.index, method="ffill")).dropna()
    pe = pe[(pe > 0) & (pe.index >= m.index[-1] - pd.DateOffset(years=years))]
    if len(pe) < min_months:
        return None
    med = float(pe.median())
    return {
        "fair_value": round(float(ttm.iloc[-1]) * med, 2),
        "median_pe": round(med, 1),
        "pe_p25": round(float(pe.quantile(0.25)), 1),
        "pe_p75": round(float(pe.quantile(0.75)), 1),
        "ttm_eps": round(float(ttm.iloc[-1]), 2),
        "months": int(len(pe)),
        "years": years,
    }


def own_history_pe_fv(config: dict, ticker: str, *, years: int = 5) -> dict[str, Any] | None:
    from signals.fetcher import fetch_ohlcv_safe
    from signals.fmp_client import fetch_earnings_surprises

    rows, err = fetch_earnings_surprises(config, ticker, limit=80)
    if err or not rows:
        return None
    return own_history_pe(rows, fetch_ohlcv_safe(ticker, "10y"), years=years)
