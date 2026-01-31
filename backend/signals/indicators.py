"""
Technical indicators and composite buy score (0-100).
- Gradient trend score (not just 0/50/100)
- RSI with asymmetric scoring: oversold boosts buy, overbought reduces
- MACD for momentum
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window, min_periods=1).mean()
    rs = np.where(loss == 0, 100.0, gain / loss)
    return pd.Series(100 - (100 / (1 + rs)), index=close.index)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_indicators(close: pd.Series) -> pd.DataFrame:
    """Compute MA20, MA50, MA200, RSI(14), MACD. Drops leading NaNs where needed."""
    df = pd.DataFrame({"close": close})

    df["MA20"] = close.rolling(20, min_periods=1).mean()
    df["MA50"] = close.rolling(50, min_periods=1).mean()
    df["MA200"] = close.rolling(200, min_periods=1).mean()
    df["RSI"] = _rsi(close, 14)
    macd_line, signal_line, hist = _macd(close, 12, 26, 9)
    df["MACD"] = macd_line
    df["MACD_signal"] = signal_line
    df["MACD_hist"] = hist

    return df


def _trend_score_gradient(row: pd.Series) -> float:
    """
    Trend score 0-100 using gradient: price vs MA50 vs MA200.
    Strong uptrend: price > MA50 > MA200 -> high score.
    Strong downtrend: price < MA50 < MA200 -> low score.
    """
    c, ma50, ma200 = row["close"], row["MA50"], row["MA200"]
    if pd.isna(ma200) or ma200 <= 0:
        return 50.0
    if pd.isna(ma50):
        return 50.0

    # Order: best = c > MA50 > MA200, worst = c < MA50 < MA200
    if c > ma50 and ma50 > ma200:
        # Distance above MA200 as % of MA200 -> cap at 100
        pct_above = (c - ma200) / ma200
        return min(100.0, 60.0 + 40.0 * min(pct_above * 10, 1.0))
    if c < ma50 and ma50 < ma200:
        pct_below = (ma200 - c) / ma200
        return max(0.0, 40.0 - 40.0 * min(pct_below * 10, 1.0))
    # Mixed: between 30 and 70
    if c > ma50:
        return 55.0
    if c < ma50:
        return 45.0
    return 50.0


def _rsi_score_asymmetric(rsi: float) -> float:
    """
    Asymmetric: oversold (RSI < 30) boosts buy score; overbought (RSI > 70) reduces.
    Returns a score contribution roughly in 0-100 (centered ~50).
    """
    if pd.isna(rsi):
        return 50.0
    if rsi <= 30:
        # Oversold -> bullish for swing buy; map 0-30 -> 60-80
        return 60.0 + (30 - rsi) / 30 * 20
    if rsi >= 70:
        # Overbought -> bearish; map 70-100 -> 20-40
        return 40.0 - (rsi - 70) / 30 * 20
    # 30-70: linear map to 40-60
    return 40.0 + (rsi - 30) / 40 * 20


def _macd_score(hist: float) -> float:
    """MACD histogram: positive -> bullish (up to 100), negative -> bearish (down to 0)."""
    if pd.isna(hist) or hist == 0:
        return 50.0
    # Normalize by typical range; clip to 0-100
    strength = np.clip(hist * 500, -50, 50)  # rough scaling
    return 50.0 + strength


def composite_score(close: pd.Series, weights: dict | None = None) -> dict:
    """
    Compute composite buy score (0-100) and component values for the latest bar.
    weights: trend, rsi, macd (default 0.5, 0.3, 0.2).
    """
    if weights is None:
        weights = {"trend": 0.5, "rsi": 0.3, "macd": 0.2}

    df = compute_indicators(close)
    if df.empty or len(df) < 2:
        return _empty_signal(close)

    row = df.iloc[-1]
    last_close = float(row["close"])
    rsi_val = float(row["RSI"])
    macd_hist = float(row["MACD_hist"])

    trend = _trend_score_gradient(row)
    rsi_contrib = _rsi_score_asymmetric(rsi_val)
    macd_contrib = _macd_score(macd_hist)

    composite = (
        weights["trend"] * trend
        + weights["rsi"] * rsi_contrib
        + weights["macd"] * macd_contrib
    )
    composite = max(0.0, min(100.0, round(composite, 1)))

    return {
        "close": last_close,
        "trend_score": round(trend, 1),
        "rsi": round(rsi_val, 1),
        "macd_hist": round(macd_hist, 4),
        "rsi_contrib": round(rsi_contrib, 1),
        "macd_contrib": round(macd_contrib, 1),
        "composite_buy": composite,
    }


def _empty_signal(close: pd.Series) -> dict:
    last = float(close.iloc[-1]) if len(close) else 0.0
    return {
        "close": last,
        "trend_score": 50.0,
        "rsi": 50.0,
        "macd_hist": 0.0,
        "rsi_contrib": 50.0,
        "macd_contrib": 50.0,
        "composite_buy": 50.0,
    }


def multi_horizon_scores(close: pd.Series) -> dict:
    """
    Short (weeks), Medium (months), Long (1–2 yrs) scores for long-term investor.
    - Short: MA20 vs MA50, RSI, 5-day momentum
    - Medium: composite (MA50/200, RSI, MACD) – main signal
    - Long: price vs MA200, MA50 vs MA200 alignment
    """
    sig = composite_score(close)
    df = compute_indicators(close)
    if df.empty or len(df) < 50:
        return {
            **sig,
            "ma20": None,
            "ma50": None,
            "short_term": 50.0,
            "medium_term": sig["composite_buy"],
            "long_term": 50.0,
            "short_suggestion": "HOLD",
            "medium_suggestion": "HOLD",
            "long_suggestion": "HOLD",
        }

    row = df.iloc[-1]
    c, ma20, ma50, ma200 = row["close"], row["MA20"], row["MA50"], row["MA200"]
    rsi_val = row["RSI"]

    # Short-term (weeks): MA20 vs MA50 + RSI
    if pd.notna(ma20) and pd.notna(ma50) and ma50 > 0:
        short_trend = 100.0 if c > ma20 > ma50 else (0.0 if c < ma20 < ma50 else 50.0)
    else:
        short_trend = 50.0
    short_rsi = _rsi_score_asymmetric(rsi_val)
    short_term = round(0.6 * short_trend + 0.4 * short_rsi, 1)
    short_term = max(0, min(100, short_term))

    # Medium-term: use composite (already computed)
    medium_term = sig["composite_buy"]

    # Long-term (1–2 yrs): price vs MA200, MA50 vs MA200
    if pd.notna(ma200) and ma200 > 0 and pd.notna(ma50):
        above_200 = (c - ma200) / ma200
        ma50_above_200 = (ma50 - ma200) / ma200 if ma200 > 0 else 0
        long_term = 50.0 + 25 * np.clip(above_200 * 20, -2, 2) + 25 * np.clip(ma50_above_200 * 20, -1, 1)
    else:
        long_term = 50.0
    long_term = round(max(0, min(100, long_term)), 1)

    def _sugg(score: float, buy: float = 65, sell: float = 35) -> str:
        if score >= buy:
            return "HOLD/ADD"
        if score <= sell:
            return "CONSIDER TRIM"
        return "HOLD"

    return {
        **sig,
        "ma20": round(float(ma20), 2) if pd.notna(ma20) else None,
        "ma50": round(float(ma50), 2) if pd.notna(ma50) else None,
        "short_term": short_term,
        "medium_term": medium_term,
        "long_term": long_term,
        "short_suggestion": _sugg(short_term),
        "medium_suggestion": _sugg(medium_term),
        "long_suggestion": _sugg(long_term),
    }
