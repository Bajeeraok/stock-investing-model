"""
Validate our indicators (next-day outlook, etc.) against external sources.
Uses Yahoo Finance analyst consensus (no API key). Optional: TipRanks/Benzinga when keys set.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_VALIDATION_TICKERS = ["SPY", "QQQ", "GLD", "SLV"]

# Yahoo Finance returns 404 "No fundamentals data found" for ETFs; skip .info and recommendation for these
_ETFS_SKIP_YAHOO_FUNDAMENTALS = frozenset({"SPY", "QQQ", "GLD", "SLV", "DIA", "IWM", "XLF", "XLK", "XLE", "XLV", "XLP", "XLY", "XLI", "XLB", "XLU"})

# Map external rating strings to our bias for comparison
_YAHOO_TO_BIAS = {
    "strongBuy": "Bullish",
    "buy": "Bullish",
    "hold": "Neutral",
    "sell": "Bearish",
    "strongSell": "Bearish",
}


def _get_yahoo_consensus(ticker: str) -> tuple[str | None, str | None]:
    """
    Get analyst consensus from Yahoo Finance (yfinance).
    Returns (bias_for_compare, display_label) or (None, None) on error.
    Skips ETFs (SPY, QQQ, etc.) to avoid Yahoo 404 "No fundamentals data found".
    """
    try:
        import yfinance as yf
    except ImportError:
        return None, None
    sym = (ticker or "").upper().split("-")[0]
    if sym in _ETFS_SKIP_YAHOO_FUNDAMENTALS:
        return None, None
    try:
        t = yf.Ticker(ticker)
        # Avoid t.info for ETFs (404); try recommendations summary first, then info
        try:
            rec = t.get_recommendations_summary()
            if rec is not None and not (hasattr(rec, "empty") and rec.empty):
                import pandas as pd
                if isinstance(rec, pd.DataFrame) and len(rec) > 0:
                    row = rec.iloc[-1]
                    best_k, best_count = None, -1
                    for k in ("strongBuy", "buy", "hold", "sell", "strongSell"):
                        if k not in row:
                            continue
                        try:
                            c = int(row[k]) if row[k] is not None else 0
                        except (TypeError, ValueError):
                            c = 0
                        if c > best_count:
                            best_count = c
                            best_k = k
                    if best_k and _YAHOO_TO_BIAS.get(best_k):
                        label = best_k.replace("strong", "Strong ").replace("Sell", "Sell").replace("Buy", "Buy")
                        return _YAHOO_TO_BIAS[best_k], label
        except Exception:
            pass
        try:
            info = t.info or {}
        except Exception:
            info = {}
        key = (info.get("recommendationKey") or "").strip().lower()
        if key:
            bias = _YAHOO_TO_BIAS.get(key)
            if bias:
                label = (info.get("recommendationKey") or key).capitalize()
                if key == "strongbuy":
                    label = "Strong Buy"
                elif key == "strongsell":
                    label = "Strong Sell"
                return bias, label
    except Exception as e:
        logger.debug("Yahoo consensus for %s: %s", ticker, e)
    return None, None


def validate_indicators_vs_external(
    next_day_outlook: list[dict[str, Any]],
    *,
    tickers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Compare our next-day bias (SPY, QQQ, GLD, SLV) to external consensus (e.g. Yahoo).
    next_day_outlook: list of {ticker, bias, pct_green?, typical_range_pct?} from dashboard.
    Returns list of {
      ticker, our_bias, source, external_rating, status ("aligned"|"divergent"|"no_data"),
      message (short human string)
    }.
    """
    syms = tickers or _VALIDATION_TICKERS
    our_by_ticker = {o["ticker"]: o.get("bias") for o in (next_day_outlook or []) if isinstance(o, dict) and o.get("ticker")}
    results = []
    for t in syms:
        our_bias = our_by_ticker.get(t)
        ext_bias, ext_label = _get_yahoo_consensus(t)
        source = "Yahoo Finance (analyst consensus)"
        if ext_bias is None:
            results.append({
                "ticker": t,
                "our_bias": our_bias,
                "source": source,
                "external_rating": None,
                "status": "no_data",
                "message": "No external consensus available",
            })
            continue
        if our_bias is None:
            results.append({
                "ticker": t,
                "our_bias": None,
                "source": source,
                "external_rating": ext_label,
                "status": "no_data",
                "message": "Our model had no outlook; external: " + (ext_label or ""),
            })
            continue
        if our_bias == ext_bias:
            status = "aligned"
            message = f"Our {our_bias} matches {source}: {ext_label}"
        else:
            status = "divergent"
            message = f"Our {our_bias} vs external {ext_label}"
        results.append({
            "ticker": t,
            "our_bias": our_bias,
            "source": source,
            "external_rating": ext_label,
            "status": status,
            "message": message,
        })
    return results
