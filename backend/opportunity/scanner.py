"""
Opportunity scanner: identify tickers with long-term growth potential on a daily basis.
Uses technical setup (strong trend, momentum, not overbought) as a first-pass filter.
Treat as "candidates to research," not buy recommendations.
"""
from __future__ import annotations

import pandas as pd

from signals.fetcher import fetch_ohlcv_safe
from signals.indicators import compute_indicators, composite_score
from signals.regime import get_regime


# Default universe: liquid S&P 500 leaders across sectors (add/remove as needed)
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "JNJ",
    "JPM", "V", "PG", "MA", "HD", "DIS", "ADBE", "CRM", "NFLX", "PEP", "KO", "WMT",
    "COST", "MCD", "NKE", "ABT", "TMO", "DHR", "AVGO", "ORCL", "LLY", "ABBV",
    "ACN", "TXN", "NEE", "PM", "BMY", "HON", "UPS", "RTX", "LOW", "AMGN", "INTC",
    "AMD", "QCOM", "INTU", "AMAT", "SBUX", "GILD", "ISRG", "MDT", "LMT", "SPY", "QQQ",
]


def _passes_long_term_criteria(
    sig: dict,
    regime: str,
    min_score: float,
    require_regime_up: bool,
    max_rsi: float,
    require_price_above_ma200: bool,
    min_macd_hist: float | None,
) -> bool:
    """Check if ticker passes long-term growth potential criteria."""
    if sig.get("composite_buy") is None or sig["composite_buy"] < min_score:
        return False
    if require_regime_up and regime != "UP":
        return False
    if sig.get("rsi") is not None and sig["rsi"] > max_rsi:
        return False  # Avoid parabolic / overbought
    if require_price_above_ma200:
        # We'd need MA200 from compute_indicators - composite_score doesn't return it
        # We'll add a simple check: if trend_score is high, price is likely above MA200
        trend = sig.get("trend_score", 0)
        if trend < 50:
            return False
    if min_macd_hist is not None and sig.get("macd_hist") is not None:
        if sig["macd_hist"] < min_macd_hist:
            return False
    return True


def run_opportunity_scan(
    universe: list[str] | None = None,
    period: str = "5y",
    min_score: float = 70,
    require_regime_up: bool = True,
    max_rsi: float = 75,
    require_price_above_ma200: bool = True,
    min_macd_hist: float | None = 0,
    up_min: float = 60,
    down_max: float = 40,
    exclude_from_watchlist: list[str] | None = None,
    max_results: int = 25,
) -> list[dict]:
    """
    Scan universe for tickers with long-term growth potential.

    Criteria (technical proxy):
    - Composite score >= min_score
    - Regime = UP (if require_regime_up)
    - RSI < max_rsi (avoid overbought)
    - Price > MA200 (if require_price_above_ma200, via trend_score)
    - MACD histogram >= min_macd_hist (momentum confirmation)

    exclude_from_watchlist: tickers to exclude (e.g. already in portfolio)
    max_results: cap output list
    """
    if universe is None or len(universe) == 0:
        universe = DEFAULT_UNIVERSE
    exclude = set(exclude_from_watchlist or [])

    opportunities = []
    for ticker in universe:
        if ticker in exclude:
            continue
        close = fetch_ohlcv_safe(ticker, period)
        if close is None:
            continue
        sig = composite_score(close)
        regime = get_regime(sig["composite_buy"], up_min, down_max)
        if not _passes_long_term_criteria(
            sig, regime, min_score, require_regime_up, max_rsi,
            require_price_above_ma200, min_macd_hist,
        ):
            continue
        # Build short reason
        reasons = []
        if sig.get("trend_score", 0) >= 70:
            reasons.append("strong uptrend")
        elif sig.get("trend_score", 0) >= 60:
            reasons.append("uptrend")
        if sig.get("rsi") is not None:
            if sig["rsi"] < 40:
                reasons.append("oversold bounce potential")
            elif sig["rsi"] < 60:
                reasons.append("RSI healthy")
        if sig.get("macd_hist", 0) and sig["macd_hist"] > 0:
            reasons.append("momentum positive")
        reason = "; ".join(reasons) if reasons else "score/regime pass"

        opportunities.append({
            "ticker": ticker,
            "close": sig["close"],
            "composite_buy": sig["composite_buy"],
            "trend_score": sig["trend_score"],
            "rsi": sig["rsi"],
            "regime": regime,
            "reason": reason,
        })

    opportunities.sort(key=lambda x: -x["composite_buy"])
    return opportunities[:max_results]
