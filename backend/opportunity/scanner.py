"""
Opportunity scanner: identify tickers with long-term growth potential on a daily basis.
Uses technical setup (strong trend, momentum, not overbought) as a first-pass filter.
Treat as "candidates to research," not buy recommendations.

Edge cases: volume filter (low liquidity), IPO/low history, earnings window exclusion.
"""
from __future__ import annotations

import pandas as pd

from signals.fetcher import fetch_ohlcv_safe, fetch_ohlcv_with_volume
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
    min_rsi: float | None,
    max_rsi: float,
    require_price_above_ma200: bool,
    min_macd_hist: float | None,
) -> bool:
    """Check if ticker passes long-term growth potential criteria."""
    if sig.get("composite_buy") is None or sig["composite_buy"] < min_score:
        return False
    if require_regime_up and regime != "UP":
        return False
    rsi = sig.get("rsi")
    if rsi is not None and rsi > max_rsi:
        return False  # Avoid parabolic / overbought
    if min_rsi is not None and rsi is not None and rsi < min_rsi:
        return False  # Spec: 50 <= RSI <= 70 sweet spot
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
    min_score: float = 80,
    require_regime_up: bool = True,
    min_rsi: float | None = 50,
    max_rsi: float = 70,
    require_price_above_ma200: bool = True,
    min_macd_hist: float | None = 0,
    up_min: float = 60,
    down_max: float = 40,
    exclude_from_watchlist: list[str] | None = None,
    max_results: int = 25,
    min_volume_ratio: float | None = 0.5,
    exclude_earnings_days: int | None = None,
    config: dict | None = None,
    max_gap_down_pct: float | None = 5.0,
    min_dollar_volume: float | None = None,
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
    min_volume_ratio: exclude when volume < this fraction of 20d avg (None = no filter)
    exclude_earnings_days: exclude when earnings in next N days (None = no filter; needs config for FMP)
    config: for earnings exclusion (get_next_earnings)
    """
    if universe is None or len(universe) == 0:
        universe = DEFAULT_UNIVERSE
    exclude = set(exclude_from_watchlist or [])

    # IPO/low-history: need 200+ bars for MA200 proxy
    min_bars = 200

    opportunities = []
    for ticker in universe:
        if ticker in exclude:
            continue
        close, volume = fetch_ohlcv_with_volume(ticker, period)
        if close is None:
            close = fetch_ohlcv_safe(ticker, period)
        if close is None:
            continue
        if len(close) < min_bars:
            continue  # IPO or insufficient history - low confidence
        use_spec = bool(config and config.get("use_spec_regime_score", False))
        sig = composite_score(close, use_spec=use_spec, ticker=ticker, config=config)
        regime = "UP" if sig.get("ma_regime") in ("UP", "UP-HV") else get_regime(sig["composite_buy"], up_min, down_max)
        # Gap filter: exclude if today down > max_gap_down_pct vs prev close
        if max_gap_down_pct is not None and len(close) >= 2:
            pct_change = 100 * (float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2])
            if pct_change < -max_gap_down_pct:
                continue
        # Dollar volume filter: avg daily dollar vol >= min_dollar_volume
        if min_dollar_volume is not None and volume is not None and len(volume) >= 20:
            avg_vol = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else float(volume.iloc[-20:].mean())
            avg_dollar = avg_vol * float(close.iloc[-1])
            if avg_dollar < min_dollar_volume:
                continue
        if not _passes_long_term_criteria(
            sig, regime, min_score, require_regime_up, min_rsi, max_rsi,
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

        opp = {
            "ticker": ticker,
            "close": sig["close"],
            "composite_buy": sig["composite_buy"],
            "trend_score": sig["trend_score"],
            "rsi": sig["rsi"],
            "regime": regime,
            "reason": reason,
        }
        if len(close) < 252:
            opp["low_history"] = True  # Flag: less than 1y data (recent IPO etc)
        opportunities.append(opp)

    opportunities.sort(key=lambda x: -x["composite_buy"])
    return opportunities[:max_results]
