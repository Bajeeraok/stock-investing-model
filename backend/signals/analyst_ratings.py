"""
Analyst rating distribution (TipRanks-style bar): FMP grades-consensus primary, Yahoo fallback.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ETFS_SKIP = frozenset({"SPY", "QQQ", "GLD", "SLV", "DIA", "IWM", "XLF", "XLK", "XLE", "XLV", "XLP", "XLY", "XLI", "XLB", "XLU"})

_RATING_KEYS = (
    ("strong_buy", ("strongBuy", "strong_buy", "analystRatingsStrongBuy", "Strong Buy")),
    ("buy", ("buy", "Buy", "analystRatingsBuy")),
    ("hold", ("hold", "Hold", "analystRatingsHold")),
    ("sell", ("sell", "Sell", "analystRatingsSell")),
    ("strong_sell", ("strongSell", "strong_sell", "analystRatingsStrongSell", "Strong Sell")),
)


def _pick_int(row: dict, aliases: tuple[str, ...]) -> int:
    for k in aliases:
        if k not in row:
            continue
        try:
            v = row[k]
            if v is None:
                continue
            return max(0, int(float(v)))
        except (TypeError, ValueError):
            continue
    return 0


def normalize_rating_distribution(raw: dict | None, source: str) -> dict | None:
    """Normalize vendor payload to {strong_buy, buy, hold, sell, strong_sell, total, source}."""
    if not raw or not isinstance(raw, dict):
        return None
    counts = {k: _pick_int(raw, aliases) for k, aliases in _RATING_KEYS}
    total = sum(counts.values())
    if total <= 0:
        return None
    bullish_pct = round(100.0 * (counts["strong_buy"] + counts["buy"]) / total, 1)
    return {
        **counts,
        "total": total,
        "bullish_pct": bullish_pct,
        "source": source,
    }


def get_yahoo_rating_distribution(ticker: str) -> dict | None:
    """Yahoo recommendations_summary counts (yfinance)."""
    sym = (ticker or "").upper().split("-")[0]
    if sym in _ETFS_SKIP:
        return None
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        t = yf.Ticker(ticker)
        rec = t.get_recommendations_summary()
        if rec is None or (hasattr(rec, "empty") and rec.empty):
            return None
        import pandas as pd

        if isinstance(rec, pd.DataFrame) and len(rec) > 0:
            row = rec.iloc[-1].to_dict()
            return normalize_rating_distribution(row, "yahoo")
    except Exception as e:
        logger.debug("Yahoo ratings for %s: %s", ticker, e)
    return None


def get_analyst_rating_distribution(config: dict, ticker: str) -> dict | None:
    """FMP grades-consensus first, then Yahoo."""
    sym = (ticker or "").upper().split("-")[0]
    if sym in _ETFS_SKIP:
        return None
    try:
        from signals.fmp_client import fetch_grades_consensus, get_api_key
        from signals.cache import cached_grades_consensus

        if get_api_key(config):
            raw = cached_grades_consensus(sym, lambda: fetch_grades_consensus(config, sym))
            dist = normalize_rating_distribution(raw, "fmp")
            if dist:
                return dist
    except Exception as e:
        logger.debug("FMP ratings for %s: %s", ticker, e)
    return get_yahoo_rating_distribution(ticker)


def street_primary_usd(fve: dict | None) -> tuple[float | None, str]:
    """FMP median → Yahoo mean → FMP range midpoint."""
    if not fve or not isinstance(fve, dict):
        return None, ""
    med = fve.get("fmp_consensus_median_usd")
    if med is not None and float(med) > 0:
        label = "FMP midpoint" if fve.get("fmp_median_is_range_midpoint") else "FMP median"
        return float(med), label
    yahoo = fve.get("yahoo_12m_mean_usd")
    if yahoo is not None and float(yahoo) > 0:
        return float(yahoo), "Yahoo 12m mean"
    lo, hi = fve.get("fmp_consensus_low_usd"), fve.get("fmp_consensus_high_usd")
    if lo is not None and hi is not None and float(lo) > 0 and float(hi) > 0:
        return (float(lo) + float(hi)) / 2.0, "FMP range midpoint"
    return None, ""


def gap_badge(pct_gap: float | None) -> str | None:
    """ok | review | caution from absolute model vs street % gap."""
    if pct_gap is None:
        return None
    a = abs(pct_gap)
    if a <= 20:
        return "ok"
    if a <= 40:
        return "review"
    return "caution"
