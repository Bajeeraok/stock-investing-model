"""
Next-day bias: state-based historical P(green) and avg move.
State = trend (above/below 20/50 MA), RSI zone, vol regime.
"""
from __future__ import annotations

import pandas as pd

from .fetcher import fetch_ohlcv_safe
from .indicators import compute_indicators


def _state(row: pd.Series, vol_20d: float | None) -> tuple[str, str, str]:
    """
    (trend, rsi_zone, vol_regime).
    trend: above_both | above_20 | below_20 | below_both
    rsi_zone: oversold | neutral | overbought
    vol_regime: low | normal | high (from vol_20d vs 60d if available; else normal)
    """
    c = row.get("close")
    ma20 = row.get("MA20")
    ma50 = row.get("MA50")
    rsi = row.get("RSI")
    if pd.isna(c) or c <= 0:
        return "unknown", "neutral", "normal"

    if pd.notna(ma20) and pd.notna(ma50) and ma20 > 0 and ma50 > 0:
        if c > ma20 and c > ma50:
            trend = "above_both"
        elif c > ma20:
            trend = "above_20"
        elif c < ma20 and c < ma50:
            trend = "below_both"
        else:
            trend = "below_20"
    else:
        trend = "unknown"

    if pd.isna(rsi):
        rsi_zone = "neutral"
    elif rsi < 35:
        rsi_zone = "oversold"
    elif rsi > 65:
        rsi_zone = "overbought"
    else:
        rsi_zone = "neutral"

    vol_regime = "normal"
    if vol_20d is not None and vol_20d > 0.25:
        vol_regime = "high"
    elif vol_20d is not None and vol_20d < 0.12:
        vol_regime = "low"

    return trend, rsi_zone, vol_regime


def _build_state_key(trend: str, rsi_zone: str, vol_regime: str) -> str:
    return f"{trend}|{rsi_zone}|{vol_regime}"


def run_next_day_backtest(
    ticker: str = "SPY",
    period: str = "5y",
    min_history: int = 100,
) -> dict:
    """
    For each day with enough history, compute state, then next-day return and green (1/0).
    Aggregate by state: count, pct_green, avg_return_pct, std_return_pct.
    Returns dict: state_stats, by_ticker.
    """
    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < min_history + 200:
        return {"error": f"Insufficient data for {ticker}", "state_stats": {}, "ticker": ticker}

    close = close.sort_index()
    df = compute_indicators(close)
    if df is None or len(df) < min_history:
        return {"error": "Insufficient indicators", "state_stats": {}, "ticker": ticker}

    returns = close.pct_change()
    vol_20d = close.pct_change().rolling(20).std()
    vol_60d = close.pct_change().rolling(60).std()

    state_buckets: dict[str, list[float]] = {}

    for i in range(min_history, len(df) - 1):
        row = df.iloc[i]
        v20 = float(vol_20d.iloc[i]) if i < len(vol_20d) and pd.notna(vol_20d.iloc[i]) else None
        trend, rsi_zone, vol_regime = _state(row, v20)
        key = _build_state_key(trend, rsi_zone, vol_regime)

        next_ret = returns.iloc[i + 1]
        if pd.isna(next_ret):
            continue
        next_ret_pct = 100 * next_ret
        green = 1.0 if next_ret > 0 else 0.0

        if key not in state_buckets:
            state_buckets[key] = []
        state_buckets[key].append((green, next_ret_pct))

    state_stats = {}
    for key, pairs in state_buckets.items():
        greens = [p[0] for p in pairs]
        rets = [p[1] for p in pairs]
        n = len(rets)
        pct_green = 100 * sum(greens) / n if n else 0
        avg_ret = sum(rets) / n if n else 0
        var = sum((r - avg_ret) ** 2 for r in rets) / n if n > 1 else 0
        std_ret = var ** 0.5
        state_stats[key] = {
            "n": n,
            "pct_green": round(pct_green, 1),
            "avg_return_pct": round(avg_ret, 2),
            "std_return_pct": round(std_ret, 2),
        }

    return {"ticker": ticker, "period": period, "state_stats": state_stats}


def get_next_day_bias(
    ticker: str,
    backtest_stats: dict | None = None,
    period: str = "2y",
) -> dict:
    """
    Current state -> look up historical pct_green and avg_return.
    backtest_stats: from run_next_day_backtest (cached). If None, run inline (slow).
    Returns: bias (Bullish|Neutral|Bearish), pct_green, avg_return_pct, typical_range_pct, state_key.
    """
    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < 100:
        return {"bias": "Neutral", "pct_green": None, "avg_return_pct": None, "typical_range_pct": None, "state_key": None}

    df = compute_indicators(close)
    if df is None or len(df) < 2:
        return {"bias": "Neutral", "pct_green": None, "avg_return_pct": None, "typical_range_pct": None, "state_key": None}

    row = df.iloc[-1]
    ret = close.pct_change().dropna()
    vol_20 = float(ret.iloc[-20:].std()) if len(ret) >= 20 else None
    trend, rsi_zone, vol_regime = _state(row, vol_20)
    state_key = _build_state_key(trend, rsi_zone, vol_regime)

    if backtest_stats is None:
        bt = run_next_day_backtest(ticker, period="5y")
        backtest_stats = bt.get("state_stats") or {}

    stats = backtest_stats.get(state_key)
    if not stats:
        # Fallback: use closest state or overall average
        for k, v in backtest_stats.items():
            stats = v
            break

    if not stats:
        return {"bias": "Neutral", "pct_green": None, "avg_return_pct": None, "typical_range_pct": None, "state_key": state_key}

    pct_green = stats.get("pct_green")
    avg_ret = stats.get("avg_return_pct")
    std_ret = stats.get("std_return_pct") or 0.5

    if pct_green is not None:
        if pct_green >= 55:
            bias = "Bullish"
        elif pct_green <= 45:
            bias = "Bearish"
        else:
            bias = "Neutral"
    else:
        bias = "Neutral"

    typical_range = round(1.3 * std_ret, 2) if std_ret else None  # ~80% band

    edge_strength = "none"
    display_note = None
    if pct_green is not None:
        if 47 <= pct_green <= 53:
            edge_strength = "none"
            display_note = "Next-day edge is minimal — no strong directional signal. Follow levels, not predictions."
        elif pct_green >= 58 or pct_green <= 42:
            edge_strength = "moderate"
        else:
            edge_strength = "weak"

    return {
        "bias": bias,
        "pct_green": pct_green,
        "avg_return_pct": avg_ret,
        "typical_range_pct": typical_range,
        "state_key": state_key,
        "edge_strength": edge_strength,
        "display_note": display_note,
    }


def next_day_outlook_for_symbols(
    symbols: list[str],
    backtest_cache: dict[str, dict] | None = None,
) -> list[dict]:
    """
    Next-day outlook for SPY, QQQ, GLD, SLV.
    backtest_cache: ticker -> { state_stats } from run_next_day_backtest (e.g. cached).
    """
    default = ["SPY", "QQQ", "GLD", "SLV"]
    syms = symbols if symbols else default
    backtest_cache = backtest_cache or {}
    out = []
    for t in syms:
        stats = backtest_cache.get(t, {}).get("state_stats")
        r = get_next_day_bias(t, backtest_stats=stats)
        r["ticker"] = t
        out.append(r)
    return out
