"""
Options market intelligence from yfinance (free, no extra API key needed).

Why options matter:
  - Put/call ratio > 1.2 = retail fear peak → contrarian buy signal
  - Low IV rank (< 25) = cheap options, market complacent → pre-breakout
  - High IV rank (> 75) = expensive options, fear spike → potential bottom
  - Max pain = where market makers profit most → gravitational price level

Signals computed:
  pc_ratio      — put volume / call volume (nearest expiry)
  atm_iv        — implied volatility of at-the-money call (nearest expiry)
  iv_rank       — atm_iv relative to 52-week realized vol range (0-100)
  max_pain      — strike with maximum total option loss for holders
  options_score — 0-1 composite (contrarian: fear + cheap IV = bullish)

All from yfinance.Ticker.option_chain() — no subscription required.
Graceful degradation: returns error dict if no options data available.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_options_signals(ticker: str) -> dict:
    """
    Fetch and score options market intelligence for ticker.

    Returns dict with:
        pc_ratio, atm_iv, iv_rank, max_pain, options_score (0-1),
        options_label (human-readable), error (if any)

    Yahoo Finance restricts options data for some tickers/regions and returns
    HTTP 401 Unauthorized.  We catch this cleanly and return a neutral 0.5
    score so the ConfidenceEngine layer degrades gracefully instead of crashing.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance not installed", "options_score": 0.5}

    # Suppress yfinance's internal HTTP-error log lines (401, 404, etc.)
    # They appear as ERROR lines in our server logs even when we handle them.
    import logging as _logging
    _yf_logger = _logging.getLogger("yfinance")
    _prev_level = _yf_logger.level
    _yf_logger.setLevel(_logging.CRITICAL)

    try:
        t = yf.Ticker(ticker)
        expiries = t.options
        if not expiries:
            return {"error": "no options data (ticker may not have listed options)", "options_score": 0.5}

        # Use nearest expiry for real-time signals
        chain = t.option_chain(expiries[0])
        calls = chain.calls
        puts  = chain.puts
    except Exception as exc:
        err_str = str(exc)
        if "401" in err_str or "Unauthorized" in err_str:
            return {"error": "options data unavailable (Yahoo Finance 401 — no subscription)", "options_score": 0.5}
        return {"error": err_str, "options_score": 0.5}
    finally:
        _yf_logger.setLevel(_prev_level)

    # Current price
    try:
        price = float(t.fast_info.last_price or t.fast_info.regularMarketPrice or 0)
    except Exception:
        price = 0.0
    if price <= 0:
        # Fall back to midpoint of first available strike
        price = float(calls["strike"].iloc[len(calls) // 2]) if not calls.empty else 100.0

    result: dict = {"ticker": ticker, "error": None}

    # ── Put/call volume ratio ─────────────────────────────────────────────
    call_vol = float(calls["volume"].fillna(0).sum())
    put_vol  = float(puts["volume"].fillna(0).sum())
    pc_ratio = round(put_vol / call_vol, 3) if call_vol > 0 else 1.0
    result["pc_ratio"] = pc_ratio

    # ── ATM implied volatility ────────────────────────────────────────────
    atm_iv = _atm_iv(calls, price)
    result["atm_iv"] = round(atm_iv, 3) if atm_iv is not None else None

    # ── IV rank (vs 1-year realized vol range) ────────────────────────────
    iv_rank = _compute_iv_rank(ticker, atm_iv) if atm_iv is not None else None
    result["iv_rank"] = round(iv_rank, 1) if iv_rank is not None else None

    # ── Max pain ──────────────────────────────────────────────────────────
    max_pain = _max_pain(calls, puts)
    result["max_pain"] = round(max_pain, 2) if max_pain is not None else None

    # ── Open interest put/call ratio ──────────────────────────────────────
    call_oi = float(calls["openInterest"].fillna(0).sum())
    put_oi  = float(puts["openInterest"].fillna(0).sum())
    pc_oi_ratio = round(put_oi / call_oi, 3) if call_oi > 0 else 1.0
    result["pc_oi_ratio"] = pc_oi_ratio

    # ── Composite options score (0-1) ─────────────────────────────────────
    # Contrarian interpretation:
    #   High P/C ratio (fear) at oversold levels  → bullish (potential bottom)
    #   Low IV rank + low P/C                     → complacency, mixed signal
    #   Very high IV rank                         → fear spike, near-term caution but potential bottom
    options_score, label = _composite_options_score(pc_ratio, iv_rank, max_pain, price)
    result["options_score"] = round(options_score, 3)
    result["options_label"] = label

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _atm_iv(calls: pd.DataFrame, price: float) -> float | None:
    """IV of the at-the-money call option."""
    if calls.empty or "impliedVolatility" not in calls.columns:
        return None
    try:
        idx = (calls["strike"] - price).abs().idxmin()
        iv = float(calls.loc[idx, "impliedVolatility"])
        return iv if np.isfinite(iv) and iv > 0 else None
    except Exception:
        return None


def _compute_iv_rank(ticker: str, current_iv: float) -> float | None:
    """
    IV rank 0-100 = where current_iv sits in its 1-year range.
    Uses 252-day realized volatility distribution as IV proxy
    (true historical IV data requires paid data feeds).
    """
    try:
        import logging as _logging
        import yfinance as yf
        _logging.getLogger("yfinance").setLevel(_logging.CRITICAL)
        data = yf.download(ticker, period="1y", progress=False, auto_adjust=True, threads=False)
        if data is None or len(data) < 60:
            return None
        close = data["Close"].dropna() if "Close" in data else data.iloc[:, 0].dropna()
        ret = close.pct_change().dropna()
        # Rolling 20d realized vol (annualized) as IV proxy
        rolling_rv = ret.rolling(20).std() * np.sqrt(252)
        rolling_rv = rolling_rv.dropna()
        if len(rolling_rv) < 20:
            return None
        rv_min = float(rolling_rv.min())
        rv_max = float(rolling_rv.max())
        if rv_max <= rv_min:
            return 50.0
        rank = (current_iv - rv_min) / (rv_max - rv_min) * 100
        return float(np.clip(rank, 0, 100))
    except Exception:
        return None


def _max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> float | None:
    """
    Max pain: strike where total option holder loss is maximised
    (= where market makers profit most; acts as gravitational price level).
    """
    try:
        strikes = sorted(set(calls["strike"].dropna()) | set(puts["strike"].dropna()))
        if not strikes:
            return None

        call_oi = dict(zip(calls["strike"], calls["openInterest"].fillna(0)))
        put_oi  = dict(zip(puts["strike"], puts["openInterest"].fillna(0)))

        min_pain, max_pain_strike = float("inf"), strikes[0]

        for test_price in strikes:
            # Loss for call holders: max(0, strike - test_price) * OI
            call_pain = sum(
                max(0.0, test_price - s) * call_oi.get(s, 0)
                for s in strikes
            )
            # Loss for put holders: max(0, test_price - strike) * OI
            put_pain = sum(
                max(0.0, s - test_price) * put_oi.get(s, 0)
                for s in strikes
            )
            total_pain = call_pain + put_pain
            if total_pain < min_pain:
                min_pain, max_pain_strike = total_pain, test_price

        return float(max_pain_strike)
    except Exception:
        return None


def _composite_options_score(
    pc_ratio: float,
    iv_rank: float | None,
    max_pain: float | None,
    current_price: float,
) -> tuple[float, str]:
    """
    Contrarian composite score (0-1):
      - Fear (high P/C) at potential bottoms is bullish
      - Complacency (low P/C + low IV) is neutral-to-bearish
      - Very high IV rank = fear spike → cautious near-term but potential reversal
    """
    score = 0.5
    parts = []

    # P/C ratio signal (contrarian)
    if pc_ratio > 1.5:
        score += 0.25
        parts.append(f"P/C {pc_ratio:.2f} (extreme fear — contrarian buy)")
    elif pc_ratio > 1.0:
        score += 0.15
        parts.append(f"P/C {pc_ratio:.2f} (elevated put buying)")
    elif pc_ratio < 0.6:
        score -= 0.10
        parts.append(f"P/C {pc_ratio:.2f} (complacency — caution)")

    # IV rank signal
    if iv_rank is not None:
        if iv_rank < 20:
            # Cheap options — market complacent; not a buy signal on its own
            score -= 0.05
            parts.append(f"IV rank {iv_rank:.0f} (cheap options — calm market)")
        elif 20 <= iv_rank <= 40:
            # Sweet spot: options affordable, some uncertainty
            score += 0.10
            parts.append(f"IV rank {iv_rank:.0f} (moderate — good risk/reward for options)")
        elif iv_rank > 70:
            # High fear — potential exhaustion
            score += 0.15
            parts.append(f"IV rank {iv_rank:.0f} (elevated fear — potential exhaustion)")

    score = round(float(np.clip(score, 0.0, 1.0)), 3)
    label = "; ".join(parts) if parts else f"P/C {pc_ratio:.2f}"
    return score, label
