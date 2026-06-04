"""
Benchmark trigger levels — SPY/QQQ support bands from MA20/50 and ATR(14).

Retail copy: "If SPY breaks $X, reduce tech 10%" style conditional rules.
"""
from __future__ import annotations

from typing import Any

from signals.fetcher import fetch_ohlcv_dataframe
from signals.volatility import atr14_from_ohlcv_df


def _levels_for_ticker(ticker: str, period: str = "6mo") -> dict[str, Any] | None:
    df = fetch_ohlcv_dataframe(ticker, period=period)
    if df is None or df.empty or "close" not in df.columns:
        return None
    close = float(df["close"].iloc[-1])
    ma20 = float(df["close"].iloc[-20:].mean()) if len(df) >= 20 else None
    ma50 = float(df["close"].iloc[-50:].mean()) if len(df) >= 50 else None
    atr = atr14_from_ohlcv_df(df) if "high" in df.columns and "low" in df.columns else None

    supports: list[dict[str, Any]] = []
    if ma20 is not None:
        supports.append({"label": "MA20 support", "price": round(ma20, 2), "type": "ma20"})
    if ma50 is not None:
        supports.append({"label": "MA50 support", "price": round(ma50, 2), "type": "ma50"})
    if atr is not None and ma20 is not None:
        stop = round(ma20 - 1.5 * atr, 2)
        supports.append({"label": "ATR stop (below MA20)", "price": stop, "type": "atr_stop"})

    primary = supports[0]["price"] if supports else None
    rules: list[str] = []
    if primary is not None:
        rules.append(f"If {ticker} closes below ${primary:.2f}, reduce new buys and tighten stops on growth.")
    if len(supports) >= 2:
        deep = supports[-1]["price"]
        rules.append(f"Break below ${deep:.2f} → defensive mode; trim extended tech/growth 10–15%.")

    chip_levels: list[dict[str, Any]] = []
    for s in supports:
        px = float(s["price"])
        dist_pct = round(100.0 * (close - px) / close, 2) if close > 0 else None
        chip_levels.append({**s, "distance_pct": dist_pct})

    return {
        "ticker": ticker,
        "last_close": round(close, 2),
        "atr14": atr,
        "supports": supports,
        "chip_levels": chip_levels,
        "primary_trigger": primary,
        "rules": rules[:2],
    }


def build_trigger_levels(
    tickers: tuple[str, ...] = ("SPY", "QQQ"),
    period: str = "6mo",
) -> dict[str, Any]:
    """SPY + QQQ trigger bands for dashboard retail decisions."""
    by_ticker: dict[str, Any] = {}
    for t in tickers:
        lv = _levels_for_ticker(t, period=period)
        if lv:
            by_ticker[t] = lv

    spy_trig = (by_ticker.get("SPY") or {}).get("primary_trigger")
    qqq_trig = (by_ticker.get("QQQ") or {}).get("primary_trigger")

    headline = None
    if spy_trig and qqq_trig:
        headline = (
            f"Watch SPY ${spy_trig:.2f} and QQQ ${qqq_trig:.2f} — breaks often drag mega-cap growth."
        )
    elif spy_trig:
        headline = f"Key SPY support: ${spy_trig:.2f} — break → reduce chase exposure."

    return {
        "levels": by_ticker,
        "headline": headline,
        "tech_rule": (
            f"If QQQ breaks ${qqq_trig:.2f}, consider trimming extended tech 10%."
            if qqq_trig
            else None
        ),
        "broad_rule": (
            f"If SPY breaks ${spy_trig:.2f}, shift to defensive posture on short-term adds."
            if spy_trig
            else None
        ),
    }
