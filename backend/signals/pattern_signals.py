"""
Pattern-based signals for near-bottom reversal detection.

Provides deterministic, rule-based pattern recognition:
  - near_bottom_score()  — 0-100 composite reversal readiness score
  - detect_double_bottom() — two lows within tolerance window
  - detect_regime()        — BULL / BEAR / TRANSITION from MA structure

Zero new dependencies: uses only pandas + numpy (same as the rest of the codebase).
All indicators are implemented from first principles so behaviour is transparent.

Integration:
    from signals.pattern_signals import near_bottom_score
    df = fetch_ohlcv_dataframe(ticker, period="2y")
    score, signals, details = near_bottom_score(df, ticker)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Internal indicator helpers (no ta library needed)
# ---------------------------------------------------------------------------

def _bollinger_lower(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.Series:
    ma  = close.rolling(window, min_periods=window).mean()
    std = close.rolling(window, min_periods=window).std(ddof=1)
    return ma - num_std * std


def _bollinger_pct_b(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.Series:
    """Percent-B: 0 = at lower band, 1 = at upper band, <0 = below lower."""
    ma  = close.rolling(window, min_periods=window).mean()
    std = close.rolling(window, min_periods=window).std(ddof=1)
    upper = ma + num_std * std
    lower = ma - num_std * std
    band_width = upper - lower
    return (close - lower) / band_width.replace(0, np.nan)


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder RSI — reuses same logic as indicators.py for consistency."""
    delta = close.diff()
    gain  = delta.where(delta > 0, 0.0)
    loss  = -delta.where(delta < 0, 0.0)
    avg_g = pd.Series(index=close.index, dtype=float)
    avg_l = pd.Series(index=close.index, dtype=float)
    if len(close) <= window:
        return pd.Series(50.0, index=close.index)
    avg_g.iloc[window - 1] = gain.iloc[:window].mean()
    avg_l.iloc[window - 1] = loss.iloc[:window].mean()
    for i in range(window, len(close)):
        avg_g.iloc[i] = (avg_g.iloc[i - 1] * (window - 1) + gain.iloc[i]) / window
        avg_l.iloc[i] = (avg_l.iloc[i - 1] * (window - 1) + loss.iloc[i]) / window
    rs = np.where(avg_l == 0, 100.0, avg_g / avg_l)
    return pd.Series(100 - (100 / (1 + rs)), index=close.index)


def _macd_histogram(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    macd  = ema_f - ema_s
    sig   = macd.ewm(span=signal, adjust=False).mean()
    return macd - sig


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

def detect_double_bottom(
    close: pd.Series,
    low: pd.Series | None = None,
    tolerance: float = 0.02,
    lookback_bars: int = 60,
) -> tuple[bool, str | None]:
    """
    Two local lows within `tolerance` of each other, separated by at least 20 bars.
    Uses `low` series if provided, otherwise uses `close`.

    Returns (detected: bool, description: str | None).
    """
    series = low if low is not None else close
    if len(series) < lookback_bars:
        return False, None

    recent_window = series.iloc[-20:]
    prior_window  = series.iloc[-lookback_bars:-20]

    if prior_window.empty:
        return False, None

    recent_min = float(recent_window.min())
    prior_min  = float(prior_window.min())

    if prior_min <= 0:
        return False, None

    if abs(recent_min - prior_min) / prior_min < tolerance:
        return True, f"Double bottom ~${recent_min:.2f} (within {tolerance*100:.0f}% of prior ~${prior_min:.2f})"

    return False, None


def detect_regime(df: pd.DataFrame) -> str:
    """
    BULL / BEAR / TRANSITION from 50-day and 200-day MA structure.
    TRANSITION is the most interesting regime for entry timing.
    """
    if "close" not in df.columns or len(df) < 50:
        return "TRANSITION"

    close = df["close"]
    sma50  = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()

    last_close = float(close.iloc[-1])
    last_50    = float(sma50.iloc[-1]) if pd.notna(sma50.iloc[-1]) else None
    last_200   = float(sma200.iloc[-1]) if pd.notna(sma200.iloc[-1]) else None

    if last_50 is None:
        return "TRANSITION"

    if last_200 is None:
        # Less than 200 bars — use 50-day only
        return "BULL" if last_close > last_50 else "BEAR"

    if last_close > last_50 > last_200:
        return "BULL"
    if last_close < last_50 < last_200:
        return "BEAR"
    return "TRANSITION"


# ---------------------------------------------------------------------------
# Core: near_bottom_score
# ---------------------------------------------------------------------------

def near_bottom_score(
    df: pd.DataFrame,
    ticker: str = "",
) -> tuple[float, list[str], dict]:
    """
    Composite 0-100 score for "near bottom and ready to reverse".

    Five components (each adds to score if condition met):
      1. 52-week low proximity  (25 pts) — price within 5% of 52w low
      2. RSI oversold + turning (25 pts) — RSI < 35 and rising over 5 bars
      3. Volume climax          (20 pts) — recent volume 1.8× 20-day average (panic exhaustion)
      4. MACD histogram turning (15 pts) — histogram increasing over last 3 bars
      5. Bollinger lower band   (15 pts) — price at or below lower 2σ band

    Requires a DataFrame with at least a "close" column.
    "low", "high", "volume" columns are used when available.

    Returns:
        score   (float 0-100)
        signals (list of human-readable strings)
        details (dict with per-component scores and raw values for debugging/display)
    """
    if df is None or df.empty or "close" not in df.columns:
        return 0.0, [], {"error": "no data"}

    close  = df["close"].dropna()
    low    = df["low"].dropna()    if "low"    in df.columns else close
    volume = df["volume"].dropna() if "volume" in df.columns else None

    if len(close) < 30:
        return 0.0, [], {"error": "insufficient bars"}

    score   = 0.0
    signals: list[str] = []
    details: dict      = {}

    price = float(close.iloc[-1])

    # ── 1. 52-week low proximity (25 pts) ─────────────────────────────────
    low_window = min(252, len(low))
    low_52w    = float(low.iloc[-low_window:].min())
    prox_52w   = (price - low_52w) / low_52w if low_52w > 0 else 1.0
    details["dist_from_52w_low_pct"] = round(prox_52w * 100, 2)
    details["low_52w"]               = round(low_52w, 2)
    if prox_52w <= 0.05:
        score += 25
        pct_label = f"{prox_52w*100:.1f}%"
        signals.append(f"Within {pct_label} of 52-week low (${low_52w:.2f})")
    elif prox_52w <= 0.12:
        score += 10
        signals.append(f"Near 52-week low (within {prox_52w*100:.1f}%)")

    # ── 2. RSI oversold + positive divergence (25 pts) ────────────────────
    rsi_series = _rsi(close, 14)
    rsi_now    = float(rsi_series.iloc[-1]) if pd.notna(rsi_series.iloc[-1]) else 50.0
    rsi_5ago   = float(rsi_series.iloc[-6]) if len(rsi_series) >= 6 and pd.notna(rsi_series.iloc[-6]) else rsi_now
    rsi_rising = rsi_now > rsi_5ago
    details["rsi"]         = round(rsi_now, 1)
    details["rsi_rising"]  = rsi_rising
    if rsi_now < 25:
        score += 25
        signals.append(f"RSI {rsi_now:.0f} — extreme oversold {'+ turning up' if rsi_rising else ''}")
    elif rsi_now < 35 and rsi_rising:
        score += 25
        signals.append(f"RSI {rsi_now:.0f} oversold + turning up (positive divergence)")
    elif rsi_now < 35:
        score += 15
        signals.append(f"RSI {rsi_now:.0f} oversold (not yet turning)")
    elif rsi_now < 45 and rsi_rising:
        score += 8
        signals.append(f"RSI {rsi_now:.0f} recovering from oversold zone")

    # ── 3. Volume climax — panic selling exhaustion (20 pts) ──────────────
    if volume is not None and len(volume) >= 23:
        avg_vol    = float(volume.iloc[-20:].mean())
        recent_vol = float(volume.iloc[-3:].mean()) if len(volume) >= 3 else avg_vol
        vol_ratio  = recent_vol / avg_vol if avg_vol > 0 else 1.0
        details["volume_ratio"] = round(vol_ratio, 2)
        if vol_ratio >= 2.5:
            score += 20
            signals.append(f"Volume climax {vol_ratio:.1f}× avg — capitulation spike")
        elif vol_ratio >= 1.8:
            score += 20
            signals.append(f"Volume surge {vol_ratio:.1f}× avg — potential exhaustion")
        elif vol_ratio <= 0.6:
            score += 10
            signals.append(f"Volume drying up ({vol_ratio:.1f}× avg) — selling pressure easing")
    else:
        details["volume_ratio"] = None

    # ── 4. MACD histogram reversing upward (15 pts) ───────────────────────
    if len(close) >= 35:
        hist = _macd_histogram(close)
        if len(hist) >= 4 and pd.notna(hist.iloc[-1]):
            h_now  = float(hist.iloc[-1])
            h_3ago = float(hist.iloc[-4]) if pd.notna(hist.iloc[-4]) else h_now
            hist_turning = h_now > h_3ago
            hist_neg     = h_now < 0
            details["macd_hist"]         = round(h_now, 5)
            details["macd_hist_turning"] = hist_turning
            if hist_turning and hist_neg:
                score += 15
                signals.append("MACD histogram reversing up (bearish momentum fading)")
            elif hist_turning:
                score += 8
                signals.append("MACD histogram strengthening")
        else:
            details["macd_hist"] = None

    # ── 5. Bollinger Band: price at or below lower band (15 pts) ──────────
    if len(close) >= 22:
        pct_b      = _bollinger_pct_b(close)
        pct_b_now  = float(pct_b.iloc[-1]) if pd.notna(pct_b.iloc[-1]) else 0.5
        lower_band = float(_bollinger_lower(close).iloc[-1]) if pd.notna(_bollinger_lower(close).iloc[-1]) else price
        details["bollinger_pct_b"]   = round(pct_b_now, 3)
        details["bollinger_lower"]   = round(lower_band, 2)
        if pct_b_now <= 0.0:
            score += 15
            signals.append(f"At/below lower Bollinger Band (${lower_band:.2f}) — stretched to downside")
        elif pct_b_now <= 0.15:
            score += 8
            signals.append(f"Near lower Bollinger Band (Percent-B: {pct_b_now:.2f})")

    # ── Double bottom bonus (up to +10 pts) ───────────────────────────────
    db_found, db_msg = detect_double_bottom(close, df.get("low") if "low" in df.columns else None)
    details["double_bottom"] = db_found
    if db_found and db_msg:
        bonus = min(10, 100 - score)
        score += bonus
        signals.append(db_msg)

    score = round(float(np.clip(score, 0, 100)), 1)
    details["price"]        = round(price, 2)
    details["ticker"]       = ticker
    details["total_score"]  = score

    return score, signals, details
